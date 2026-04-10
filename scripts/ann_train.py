from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, cast

import numpy as np


def _bootstrap_sys_path() -> Path:
    here = Path(__file__).resolve()
    app_root = here.parents[1]
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    return app_root


APP_ROOT = _bootstrap_sys_path()

from src.ann.config import ANNTrainingConfig, SchedulerConfig  # noqa: E402
from src.ann.dataset import build_training_dataset  # noqa: E402
from src.ann.feature_selection import (  # noqa: E402
    correlation_filter,
    model_importance_prune,
    recursive_feature_elimination,
)
from src.ann.trainer import train_ann_regressor  # noqa: E402
from src.config import paths  # noqa: E402


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train ANN regressor from ANN input feature store."
    )
    p.add_argument(
        "--store-path",
        default=str(paths.OUT_I_CALC_DIR / "stores" / "ann_input_features.sqlite"),
    )
    p.add_argument("--raw-tickers-dir", default=str(paths.DATA_TICKERS_DIR))
    p.add_argument(
        "--tickers",
        nargs="+",
        default=["TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"],
    )

    p.add_argument("--learning-rate", type=float, default=1e-3)
    p.add_argument(
        "--scheduler-kind",
        choices=["none", "step", "cosine", "reduce_on_plateau"],
        default="none",
    )
    p.add_argument("--scheduler-step-size", type=int, default=10)
    p.add_argument("--scheduler-gamma", type=float, default=0.8)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--epochs", type=int, default=600)
    p.add_argument("--early-stopping-patience", type=int, default=12)
    p.add_argument("--early-stopping-min-delta", type=float, default=1e-5)
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--width", type=int, default=32)
    p.add_argument("--dropout", type=float, default=0.10)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--window-length", type=int, default=5)
    p.add_argument("--lag-depth", type=int, default=4)
    p.add_argument(
        "--train-end-date",
        type=str,
        default="",
        help="Inclusive training end date (YYYY-MM-DD)",
    )
    p.add_argument(
        "--target-mode",
        choices=["magnitude", "sgn"],
        default="magnitude",
        help="Training target mode: return magnitude or sign-only",
    )
    p.add_argument("--forecast-horizon", type=int, default=1)

    p.add_argument(
        "--feature-selection",
        choices=["none", "correlation", "importance", "rfe"],
        default="none",
    )
    p.add_argument("--corr-threshold", type=float, default=0.95)
    p.add_argument("--importance-keep-ratio", type=float, default=0.5)
    p.add_argument("--rfe-min-features", type=int, default=12)
    p.add_argument("--rfe-drop-count", type=int, default=4)
    p.add_argument(
        "--feature-allowlist-file",
        type=str,
        default="",
        help="Optional JSON file with selected_columns list to constrain ANN inputs",
    )
    p.add_argument(
        "--save-selected-features-file",
        type=str,
        default="",
        help="Optional JSON output path to persist selected feature set",
    )

    p.add_argument(
        "--output-dir", default=str(paths.OUT_I_CALC_DIR / "ann" / "training")
    )
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(list(argv) if argv is not None else None)


def _utc_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _select_columns(
    *,
    method: str,
    X,
    y,
    columns: list[str],
    corr_threshold: float,
    importance_keep_ratio: float,
    rfe_min_features: int,
    rfe_drop_count: int,
) -> tuple[list[str], list[dict[str, object]]]:
    history: list[dict[str, object]] = []
    if method == "none":
        return list(columns), history
    if method == "correlation":
        selected = correlation_filter(X, columns, threshold=float(corr_threshold))
        history.append({"method": "correlation", "selected": len(selected)})
        return selected, history
    if method == "importance":
        selected = model_importance_prune(
            X,
            y,
            columns,
            keep_ratio=float(importance_keep_ratio),
        )
        history.append({"method": "importance", "selected": len(selected)})
        return selected, history
    rfe = recursive_feature_elimination(
        X,
        y,
        columns,
        min_features=max(1, int(rfe_min_features)),
        drop_count_per_round=max(1, int(rfe_drop_count)),
    )
    return rfe.selected_columns, list(rfe.history)


def _load_feature_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(payload, list):
        return {str(x).strip() for x in payload if str(x).strip()}
    if isinstance(payload, dict):
        values = payload.get("selected_columns")
        if isinstance(values, list):
            return {str(x).strip() for x in values if str(x).strip()}
    return set()


def _rank_feature_impacts(
    X: np.ndarray,
    y: np.ndarray,
    columns: list[str],
    *,
    top_n: int = 5,
) -> list[dict[str, object]]:
    x = np.asarray(X, dtype=float)
    t = np.asarray(y, dtype=float).reshape(-1)
    if x.ndim != 2 or x.shape[0] == 0 or x.shape[1] == 0:
        return []

    ranked: list[tuple[str, float]] = []
    for i, name in enumerate(columns):
        xi = x[:, i]
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            corr = np.corrcoef(xi, t)[0, 1]
        score = abs(float(corr)) if np.isfinite(corr) else 0.0
        ranked.append((str(name), score))

    ranked.sort(key=lambda item: item[1], reverse=True)
    top = ranked[: max(1, int(top_n))]
    return [
        {
            "rank": int(idx + 1),
            "feature": str(name),
            "impact_score": float(score),
        }
        for idx, (name, score) in enumerate(top)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    scheduler = SchedulerConfig(
        kind=cast(Any, str(args.scheduler_kind)),
        step_size=int(args.scheduler_step_size),
        gamma=float(args.scheduler_gamma),
    )
    config = ANNTrainingConfig(
        learning_rate=float(args.learning_rate),
        batch_size=int(args.batch_size),
        epochs=int(args.epochs),
        early_stopping_patience=int(args.early_stopping_patience),
        early_stopping_min_delta=float(args.early_stopping_min_delta),
        depth=int(args.depth),
        width=int(args.width),
        dropout=float(args.dropout),
        weight_decay=float(args.weight_decay),
        window_length=int(args.window_length),
        lag_depth=int(args.lag_depth),
        forecast_horizon=int(args.forecast_horizon),
        scheduler=scheduler,
    )

    dataset = build_training_dataset(
        store_path=Path(args.store_path),
        raw_tickers_dir=Path(args.raw_tickers_dir),
        tickers=[str(x).strip().upper() for x in args.tickers],
        config=config,
        train_end_date=str(args.train_end_date or "").strip() or None,
        target_mode=str(args.target_mode or "magnitude").strip().lower(),
    )
    if dataset.X.shape[0] == 0 or dataset.X.shape[1] == 0:
        print("[ann_train] no training rows or features available")
        return 2

    dataset_X = dataset.X
    dataset_columns = list(dataset.feature_columns)
    allowlist_path = Path(str(args.feature_allowlist_file or "").strip())
    allowlist_used = False
    if str(args.feature_allowlist_file or "").strip():
        allowed = _load_feature_allowlist(allowlist_path)
        if allowed:
            idx = [i for i, name in enumerate(dataset_columns) if name in allowed]
            if not idx:
                print("[ann_train] feature allowlist removed all available features")
                return 2
            dataset_X = dataset_X[:, idx]
            dataset_columns = [dataset_columns[i] for i in idx]
            allowlist_used = True

    selected_columns, selection_history = _select_columns(
        method=str(args.feature_selection),
        X=dataset_X,
        y=dataset.y,
        columns=dataset_columns,
        corr_threshold=float(args.corr_threshold),
        importance_keep_ratio=float(args.importance_keep_ratio),
        rfe_min_features=int(args.rfe_min_features),
        rfe_drop_count=int(args.rfe_drop_count),
    )
    idx_map = {name: i for i, name in enumerate(dataset_columns)}
    selected_idx = [idx_map[name] for name in selected_columns if name in idx_map]
    if not selected_idx:
        print("[ann_train] feature selection removed all features")
        return 2

    X_sel = dataset_X[:, selected_idx]
    result = train_ann_regressor(X_sel, dataset.y, config=config, seed=int(args.seed))
    top_feature_impacts = _rank_feature_impacts(
        X_sel,
        dataset.y,
        selected_columns,
        top_n=5,
    )

    out_dir = Path(args.output_dir).resolve() / f"run_{_utc_tag()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    config_payload = {
        "training_config": config.to_dict(),
        "feature_selection": {
            "method": str(args.feature_selection),
            "corr_threshold": float(args.corr_threshold),
            "importance_keep_ratio": float(args.importance_keep_ratio),
            "rfe_min_features": int(args.rfe_min_features),
            "rfe_drop_count": int(args.rfe_drop_count),
            "allowlist_path": str(allowlist_path) if allowlist_used else None,
        },
        "tickers": [str(x).strip().upper() for x in args.tickers],
        "seed": int(args.seed),
        "train_end_date": str(args.train_end_date or "").strip() or None,
        "target_mode": str(args.target_mode or "magnitude").strip().lower(),
    }
    (out_dir / "config.json").write_text(
        json.dumps(config_payload, indent=2), encoding="utf-8"
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(result.metrics, indent=2), encoding="utf-8"
    )
    (out_dir / "selected_features.json").write_text(
        json.dumps(
            {
                "selected_count": len(selected_columns),
                "selected_columns": selected_columns,
                "history": selection_history,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "top_feature_impacts.json").write_text(
        json.dumps(top_feature_impacts, indent=2),
        encoding="utf-8",
    )
    (out_dir / "training_history.json").write_text(
        json.dumps(
            {
                "best_epoch": result.best_epoch,
                "epochs_ran": result.epochs_ran,
                "train_loss_history": result.train_loss_history,
                "val_loss_history": result.val_loss_history,
                "learning_rate_history": result.learning_rate_history,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = {
        "run_dir": str(out_dir),
        "rows": int(dataset.X.shape[0]),
        "features_before_selection": int(len(dataset_columns)),
        "features_after_selection": int(len(selected_columns)),
        "metrics": result.metrics,
        "best_epoch": int(result.best_epoch),
        "top_feature_impacts": top_feature_impacts,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print(f"[ann_train] run_dir={out_dir}")
    print(f"[ann_train] rows={summary['rows']}")
    print(
        "[ann_train] features="
        f"{summary['features_after_selection']}/{summary['features_before_selection']}"
    )
    print(f"[ann_train] r2={result.metrics.get('r2', 0.0):.6f}")
    for item in top_feature_impacts:
        impact_raw = item.get("impact_score")
        impact = float(impact_raw) if isinstance(impact_raw, (int, float)) else 0.0
        print(
            "[ann_train] top_feature "
            f"#{item.get('rank')} {item.get('feature')} score={impact:.6f}"
        )

    save_selected_path = Path(str(args.save_selected_features_file or "").strip())
    if str(args.save_selected_features_file or "").strip():
        save_selected_path.parent.mkdir(parents=True, exist_ok=True)
        save_selected_path.write_text(
            json.dumps(
                {
                    "source_run_dir": str(out_dir),
                    "selected_count": len(selected_columns),
                    "selected_columns": selected_columns,
                    "generated_at": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[ann_train] saved_selected_features={save_selected_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
