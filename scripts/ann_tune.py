from __future__ import annotations

import argparse
import csv
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
    p = argparse.ArgumentParser(description="Run ANN tuning trials.")
    p.add_argument(
        "--store-path",
        default=str(paths.OUT_I_CALC_DIR / "stores" / "ann_input_features.sqlite"),
    )
    p.add_argument("--raw-tickers-dir", default=str(paths.DATA_TICKERS_DIR))
    p.add_argument(
        "--rounds-dir",
        default=str(paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR),
    )
    p.add_argument(
        "--tickers",
        nargs="+",
        default=["TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"],
    )
    p.add_argument(
        "--target-modes",
        nargs="+",
        default=["magnitude", "sgn"],
        choices=["magnitude", "sgn"],
    )
    p.add_argument(
        "--tune-scope",
        choices=["matrix", "global"],
        default="matrix",
        help="matrix=tune per ticker and target mode; global=tune one shared setup",
    )
    p.add_argument(
        "--train-end-date",
        type=str,
        default="",
        help="Inclusive training end date (YYYY-MM-DD)",
    )
    p.add_argument("--max-trials", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output-dir", default=str(paths.OUT_I_CALC_DIR / "ann" / "tuning"))
    return p.parse_args(list(argv) if argv is not None else None)


def _utc_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _sample_config(rng: np.random.Generator) -> dict[str, Any]:
    return {
        "learning_rate": float(rng.choice([1e-4, 3e-4, 1e-3, 3e-3, 1e-2])),
        "scheduler_kind": str(rng.choice(["none", "step", "cosine"])),
        "batch_size": int(rng.choice([16, 32, 64])),
        "epochs": int(rng.choice([60, 100, 140])),
        "early_stopping_patience": int(rng.choice([8, 12, 16])),
        "depth": int(rng.choice([1, 2, 3])),
        "width": int(rng.choice([16, 32, 64])),
        "dropout": float(rng.choice([0.0, 0.1, 0.2])),
        "weight_decay": float(rng.choice([0.0, 1e-5, 1e-4, 1e-3])),
        "window_length": int(rng.choice([3, 5, 8])),
        "lag_depth": int(rng.choice([2, 4, 7])),
        "feature_selection": str(
            rng.choice(["none", "correlation", "importance", "rfe"])
        ),
    }


def _select_columns(
    method: str,
    X: np.ndarray,
    y: np.ndarray,
    columns: list[str],
) -> list[str]:
    if method == "none":
        return list(columns)
    if method == "correlation":
        return correlation_filter(X, columns, threshold=0.95)
    if method == "importance":
        return model_importance_prune(X, y, columns, keep_ratio=0.5)
    rfe = recursive_feature_elimination(
        X,
        y,
        columns,
        min_features=max(8, min(24, len(columns))),
        drop_count_per_round=4,
    )
    return rfe.selected_columns


def _run_trials_for_setup(
    *,
    rng: np.random.Generator,
    setup_tickers: list[str],
    target_mode: str,
    max_trials: int,
    seed: int,
    store_path: Path,
    raw_tickers_dir: Path,
    rounds_dir: Path,
    train_end_date: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trial in range(1, max(1, int(max_trials)) + 1):
        sampled = _sample_config(rng)
        scheduler = SchedulerConfig(kind=cast(Any, str(sampled["scheduler_kind"])))
        cfg = ANNTrainingConfig(
            learning_rate=float(sampled["learning_rate"]),
            batch_size=int(sampled["batch_size"]),
            epochs=int(sampled["epochs"]),
            early_stopping_patience=int(sampled["early_stopping_patience"]),
            depth=int(sampled["depth"]),
            width=int(sampled["width"]),
            dropout=float(sampled["dropout"]),
            weight_decay=float(sampled["weight_decay"]),
            window_length=int(sampled["window_length"]),
            lag_depth=int(sampled["lag_depth"]),
            scheduler=scheduler,
        )

        ds = build_training_dataset(
            store_path=store_path,
            raw_tickers_dir=raw_tickers_dir,
            tickers=setup_tickers,
            config=cfg,
            rounds_dir=rounds_dir,
            train_end_date=train_end_date,
            target_mode=target_mode,
        )
        if ds.X.shape[0] == 0 or ds.X.shape[1] == 0:
            continue

        selected = _select_columns(
            str(sampled["feature_selection"]), ds.X, ds.y, ds.feature_columns
        )
        idx_map = {name: i for i, name in enumerate(ds.feature_columns)}
        selected_idx = [idx_map[name] for name in selected if name in idx_map]
        if not selected_idx:
            continue

        result = train_ann_regressor(
            ds.X[:, selected_idx],
            ds.y,
            config=cfg,
            seed=int(seed) + int(trial),
        )
        row = {
            "trial": int(trial),
            "target_mode": str(target_mode),
            "tickers": "|".join(setup_tickers),
            **sampled,
            "features_before": int(len(ds.feature_columns)),
            "features_after": int(len(selected_idx)),
            "r2": float(result.metrics.get("r2", 0.0)),
            "mae": float(result.metrics.get("mae", 0.0)),
            "rmse": float(result.metrics.get("rmse", 0.0)),
            "mape": float(result.metrics.get("mape", 0.0)),
            "directional_accuracy": float(
                result.metrics.get("directional_accuracy", 0.0)
            ),
        }
        rows.append(row)
    return rows


def _rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda x: (-float(x["r2"]), float(x["rmse"])))


def _best_config_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "learning_rate": row["learning_rate"],
        "batch_size": row["batch_size"],
        "epochs": row["epochs"],
        "early_stopping_patience": row["early_stopping_patience"],
        "depth": row["depth"],
        "width": row["width"],
        "dropout": row["dropout"],
        "weight_decay": row["weight_decay"],
        "window_length": row["window_length"],
        "lag_depth": row["lag_depth"],
        "scheduler_kind": row["scheduler_kind"],
        "feature_selection": row["feature_selection"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    rng = np.random.default_rng(int(args.seed))
    tickers = [str(x).strip().upper() for x in args.tickers if str(x).strip()]
    target_modes = [str(x).strip().lower() for x in args.target_modes if str(x).strip()]
    store_path = Path(args.store_path).resolve()
    raw_tickers_dir = Path(args.raw_tickers_dir).resolve()
    rounds_dir = Path(args.rounds_dir).resolve()
    train_end_date = str(args.train_end_date or "").strip() or None

    all_rows: list[dict[str, Any]] = []
    matrix_best: dict[str, dict[str, dict[str, Any]]] = {}

    if str(args.tune_scope) == "global":
        mode = target_modes[0] if target_modes else "magnitude"
        trial_rows = _run_trials_for_setup(
            rng=rng,
            setup_tickers=tickers,
            target_mode=mode,
            max_trials=int(args.max_trials),
            seed=int(args.seed),
            store_path=store_path,
            raw_tickers_dir=raw_tickers_dir,
            rounds_dir=rounds_dir,
            train_end_date=train_end_date,
        )
        if not trial_rows:
            print("[ann_tune] no trials produced usable datasets")
            return 2
        ranked = _rank(trial_rows)
        all_rows.extend(ranked)
    else:
        for ticker in tickers:
            matrix_best[ticker] = {}
            for mode in target_modes:
                trial_rows = _run_trials_for_setup(
                    rng=rng,
                    setup_tickers=[ticker],
                    target_mode=mode,
                    max_trials=int(args.max_trials),
                    seed=int(args.seed),
                    store_path=store_path,
                    raw_tickers_dir=raw_tickers_dir,
                    rounds_dir=rounds_dir,
                    train_end_date=train_end_date,
                )
                if not trial_rows:
                    continue
                ranked = _rank(trial_rows)
                all_rows.extend(ranked)
                best = ranked[0]
                matrix_best[ticker][mode] = {
                    **_best_config_fields(best),
                    "r2": best["r2"],
                    "mae": best["mae"],
                    "rmse": best["rmse"],
                    "mape": best["mape"],
                    "directional_accuracy": best["directional_accuracy"],
                    "features_before": best["features_before"],
                    "features_after": best["features_after"],
                }

        if not all_rows:
            print("[ann_tune] no trials produced usable datasets")
            return 2

    ranked_all = _rank(all_rows)
    best = ranked_all[0]

    out_dir = Path(args.output_dir).resolve() / f"tune_{_utc_tag()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    trials_path = out_dir / "trials.csv"
    with trials_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ranked_all[0].keys()))
        writer.writeheader()
        writer.writerows(ranked_all)

    best_config = _best_config_fields(best)
    (out_dir / "best_config.json").write_text(
        json.dumps(best_config, indent=2),
        encoding="utf-8",
    )
    (out_dir / "best_summary.json").write_text(
        json.dumps(best, indent=2),
        encoding="utf-8",
    )

    if matrix_best:
        (out_dir / "best_config_matrix.json").write_text(
            json.dumps(matrix_best, indent=2),
            encoding="utf-8",
        )

    setup_count = sum(len(v) for v in matrix_best.values()) if matrix_best else 1

    print(f"[ann_tune] output_dir={out_dir}")
    print(f"[ann_tune] trials={len(ranked_all)}")
    print(f"[ann_tune] setups={setup_count}")
    print(f"[ann_tune] best_r2={float(best['r2']):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
