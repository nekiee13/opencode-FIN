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
from src.ann.metrics import regression_metrics  # noqa: E402
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
    p.add_argument(
        "--validation-scheme",
        choices=["walk_forward", "single_split"],
        default="walk_forward",
    )
    p.add_argument("--cv-folds", type=int, default=3)
    p.add_argument("--min-fold-size", type=int, default=3)
    p.add_argument("--min-train-size", type=int, default=12)
    p.add_argument("--min-samples", type=int, default=30)
    p.add_argument("--min-class-count", type=int, default=8)
    p.add_argument("--min-target-variance", type=float, default=1e-5)
    p.add_argument("--sgn-min-improvement", type=float, default=0.03)
    p.add_argument("--magnitude-min-improvement", type=float, default=0.03)
    p.add_argument("--max-trials", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output-dir", default=str(paths.OUT_I_CALC_DIR / "ANN" / "tuning"))
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


def _as_finite_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(out):
        return default
    return out


def _compute_setup_diagnostics(
    y: np.ndarray,
    *,
    target_mode: str,
) -> dict[str, Any]:
    mode = str(target_mode or "").strip().lower()
    yt = np.asarray(y, dtype=float).reshape(-1)
    sample_count = int(yt.shape[0])
    out: dict[str, Any] = {
        "sample_count": sample_count,
    }
    if sample_count <= 0:
        if mode == "sgn":
            out.update(
                {
                    "sgn_positive_count": 0,
                    "sgn_negative_count": 0,
                    "sgn_positive_ratio": 0.0,
                    "sgn_negative_ratio": 0.0,
                }
            )
        else:
            out.update(
                {
                    "target_variance": 0.0,
                    "target_std": 0.0,
                }
            )
        return out

    if mode == "sgn":
        pos = int(np.sum(yt > 0.0))
        neg = int(np.sum(yt < 0.0))
        total = max(1, pos + neg)
        out.update(
            {
                "sgn_positive_count": pos,
                "sgn_negative_count": neg,
                "sgn_positive_ratio": float(pos / total),
                "sgn_negative_ratio": float(neg / total),
            }
        )
    else:
        var = float(np.var(yt))
        std = float(np.std(yt))
        out.update(
            {
                "target_variance": var if np.isfinite(var) else 0.0,
                "target_std": std if np.isfinite(std) else 0.0,
            }
        )
    return out


def _assess_sufficiency(
    diagnostics: dict[str, Any],
    *,
    target_mode: str,
    min_samples: int,
    min_class_count: int,
    min_target_variance: float,
) -> tuple[bool, list[str]]:
    mode = str(target_mode or "").strip().lower()
    reasons: list[str] = []

    sample_count = int(diagnostics.get("sample_count") or 0)
    if sample_count < int(min_samples):
        reasons.append(f"min_samples:{sample_count}<{int(min_samples)}")

    if mode == "sgn":
        pos = int(diagnostics.get("sgn_positive_count") or 0)
        neg = int(diagnostics.get("sgn_negative_count") or 0)
        if pos < int(min_class_count) or neg < int(min_class_count):
            reasons.append(
                f"min_class_count:pos={pos},neg={neg}<min={int(min_class_count)}"
            )
    else:
        variance = _as_finite_float(diagnostics.get("target_variance"), 0.0)
        if variance < float(min_target_variance):
            reasons.append(
                f"min_target_variance:{variance:.6g}<{float(min_target_variance):.6g}"
            )

    return (len(reasons) == 0), reasons


def _leakage_check(feature_columns: list[str]) -> dict[str, Any]:
    risky_tokens = (
        "target",
        "future",
        "tplus",
        "day3",
        "actual_close",
        "weighted_ensemble",
    )
    suspect = [
        col
        for col in feature_columns
        if any(token in str(col).lower() for token in risky_tokens)
    ]
    all_lagged = (
        all("__lag" in str(col) for col in feature_columns) if feature_columns else True
    )
    passed = (len(suspect) == 0) and all_lagged
    reasons: list[str] = []
    if suspect:
        reasons.append("suspect_feature_names")
    if not all_lagged:
        reasons.append("non_lagged_feature_columns_present")
    return {
        "passed": bool(passed),
        "reasons": reasons,
        "suspect_features": suspect[:10],
    }


def _validation_slices(
    n_rows: int,
    *,
    scheme: str,
    cv_folds: int,
    min_fold_size: int,
    min_train_size: int,
) -> list[tuple[slice, slice]]:
    n = int(n_rows)
    if n <= 1:
        return []

    mode = str(scheme or "walk_forward").strip().lower()
    val_n = max(1, int(min_fold_size))

    if mode == "single_split":
        val_n = min(val_n, n - 1)
        train_n = n - val_n
        if train_n <= 0:
            return []
        return [(slice(0, train_n), slice(train_n, n))]

    start_train_end = max(1, int(min_train_size))
    max_train_end = n - val_n
    if start_train_end > max_train_end:
        return []

    fold_count = max(1, int(cv_folds))
    positions = np.linspace(
        start_train_end,
        max_train_end,
        num=fold_count,
        dtype=int,
    ).tolist()

    slices: list[tuple[slice, slice]] = []
    seen: set[tuple[int, int]] = set()
    for train_end in positions:
        train_end_i = int(train_end)
        val_end = train_end_i + val_n
        if train_end_i < 1 or val_end > n:
            continue
        key = (train_end_i, val_end)
        if key in seen:
            continue
        seen.add(key)
        slices.append((slice(0, train_end_i), slice(train_end_i, val_end)))
    return slices


def _baseline_metrics_for_fold(
    *,
    target_mode: str,
    y_train: np.ndarray,
    y_val: np.ndarray,
) -> dict[str, Any]:
    mode = str(target_mode or "").strip().lower()
    yt = np.asarray(y_train, dtype=float).reshape(-1)
    yv = np.asarray(y_val, dtype=float).reshape(-1)
    if yv.size == 0:
        empty = regression_metrics(yv, yv)
        return {
            "selected": "none",
            "selected_metrics": empty,
            "candidates": {"none": empty},
        }

    if mode == "magnitude":
        persistence_value = float(yt[-1]) if yt.size > 0 else 0.0
        median_value = float(np.median(yt)) if yt.size > 0 else 0.0
        pred_persistence = np.full(yv.shape, persistence_value, dtype=float)
        pred_median = np.full(yv.shape, median_value, dtype=float)
        persistence_metrics = regression_metrics(yv, pred_persistence)
        median_metrics = regression_metrics(yv, pred_median)
        candidates = {
            "persistence": persistence_metrics,
            "median": median_metrics,
        }
        selected = min(
            candidates.items(),
            key=lambda item: _as_finite_float(item[1].get("rmse"), float("inf")),
        )
        return {
            "selected": str(selected[0]),
            "selected_metrics": dict(selected[1]),
            "candidates": candidates,
        }

    pos = int(np.sum(yt > 0.0))
    neg = int(np.sum(yt < 0.0))
    majority_label = 1.0 if pos >= neg else -1.0
    pred_majority = np.full(yv.shape, majority_label, dtype=float)

    pred_prior = np.empty(yv.shape, dtype=float)
    prev = float(yt[-1]) if yt.size > 0 else majority_label
    for idx in range(yv.shape[0]):
        pred_prior[idx] = prev
        prev = float(yv[idx])

    majority_metrics = regression_metrics(yv, pred_majority)
    prior_metrics = regression_metrics(yv, pred_prior)
    candidates = {
        "majority_class": majority_metrics,
        "prior_sign": prior_metrics,
    }
    selected = max(
        candidates.items(),
        key=lambda item: (
            _as_finite_float(item[1].get("directional_accuracy"), 0.0),
            -_as_finite_float(item[1].get("mae"), float("inf")),
        ),
    )
    return {
        "selected": str(selected[0]),
        "selected_metrics": dict(selected[1]),
        "candidates": candidates,
    }


def _improvement_from_baseline(
    *,
    target_mode: str,
    ann_metrics: dict[str, float],
    baseline_metrics: dict[str, Any],
) -> dict[str, float]:
    mode = str(target_mode or "").strip().lower()
    selected = dict(baseline_metrics.get("selected_metrics") or {})
    if mode == "sgn":
        ann_da = _as_finite_float(ann_metrics.get("directional_accuracy"), 0.0)
        base_da = _as_finite_float(selected.get("directional_accuracy"), 0.0)
        delta = ann_da - base_da
        return {
            "directional_accuracy_delta": float(delta),
            "score": float(delta),
        }

    ann_rmse = _as_finite_float(ann_metrics.get("rmse"), float("inf"))
    base_rmse = _as_finite_float(selected.get("rmse"), float("inf"))
    if not np.isfinite(ann_rmse) or not np.isfinite(base_rmse):
        return {
            "rmse_delta": 0.0,
            "rmse_delta_pct": 0.0,
            "score": 0.0,
        }
    delta_abs = base_rmse - ann_rmse
    delta_pct = delta_abs / base_rmse if base_rmse > 1e-12 else 0.0
    return {
        "rmse_delta": float(delta_abs),
        "rmse_delta_pct": float(delta_pct),
        "score": float(delta_pct),
    }


def _mean_metric_dict(dicts: list[dict[str, Any]]) -> dict[str, float]:
    if not dicts:
        return {}
    keys = sorted({k for item in dicts for k in item.keys()})
    out: dict[str, float] = {}
    for key in keys:
        values = [_as_finite_float(item.get(key), np.nan) for item in dicts]
        arr = np.array(values, dtype=float)
        arr = arr[np.isfinite(arr)]
        out[key] = float(np.mean(arr)) if arr.size else 0.0
    return out


def _std_metric_dict(dicts: list[dict[str, Any]]) -> dict[str, float]:
    if not dicts:
        return {}
    keys = sorted({k for item in dicts for k in item.keys()})
    out: dict[str, float] = {}
    for key in keys:
        values = [_as_finite_float(item.get(key), np.nan) for item in dicts]
        arr = np.array(values, dtype=float)
        arr = arr[np.isfinite(arr)]
        out[key] = float(np.std(arr)) if arr.size else 0.0
    return out


def _scoring_policy_for_mode(
    *,
    target_mode: str,
    sgn_min_improvement: float,
    magnitude_min_improvement: float,
) -> dict[str, Any]:
    mode = str(target_mode or "").strip().lower()
    if mode == "sgn":
        return {
            "objective": "directional_accuracy",
            "ranking": [
                "status_priority",
                "improvement_vs_baseline desc",
                "directional_accuracy desc",
                "mae asc",
                "rmse asc",
                "r2 desc",
            ],
            "baseline_gate": {
                "metric": "directional_accuracy_delta",
                "min_improvement": float(sgn_min_improvement),
            },
        }
    return {
        "objective": "error_minimization",
        "ranking": [
            "status_priority",
            "improvement_vs_baseline desc",
            "rmse asc",
            "mae asc",
            "r2 desc",
            "directional_accuracy desc",
        ],
        "baseline_gate": {
            "metric": "rmse_delta_pct",
            "min_improvement": float(magnitude_min_improvement),
        },
    }


def _status_priority(status: Any) -> int:
    name = str(status or "").strip().lower()
    if name == "healthy":
        return 0
    if name == "fails_baseline":
        return 1
    return 2


def _rank_key_for_mode(
    row: dict[str, Any],
    target_mode: str,
) -> tuple[float, float, float, float, float, float]:
    mode = str(target_mode or "").strip().lower()
    r2 = _as_finite_float(row.get("r2"), float("-inf"))
    mae = _as_finite_float(row.get("mae"), float("inf"))
    rmse = _as_finite_float(row.get("rmse"), float("inf"))
    directional_accuracy = _as_finite_float(row.get("directional_accuracy"), 0.0)
    improvement = _as_finite_float(row.get("improvement_vs_baseline"), -1e9)
    if not np.isfinite(improvement) or improvement <= -1e8:
        if mode == "sgn":
            improvement = _as_finite_float(
                row.get("improvement_directional_accuracy"),
                -1e9,
            )
        else:
            improvement = _as_finite_float(row.get("improvement_rmse_pct"), -1e9)
    status_rank = float(_status_priority(row.get("status")))

    if mode == "sgn":
        return (
            status_rank,
            -improvement,
            -directional_accuracy,
            mae,
            rmse,
            -r2,
        )
    return (
        status_rank,
        -improvement,
        rmse,
        mae,
        -r2,
        -directional_accuracy,
    )


def _rank(
    rows: list[dict[str, Any]],
    *,
    target_mode: str | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    mode = str(target_mode or "").strip().lower()
    if not mode:
        inferred = {str(x.get("target_mode") or "").strip().lower() for x in rows}
        if len(inferred) == 1 and next(iter(inferred)) in {"magnitude", "sgn"}:
            mode = next(iter(inferred))

    if mode in {"magnitude", "sgn"}:
        return sorted(rows, key=lambda x: _rank_key_for_mode(x, mode))

    return sorted(
        rows,
        key=lambda x: (
            _status_priority(x.get("status")),
            -_as_finite_float(x.get("improvement_vs_baseline"), -1e9),
            -_as_finite_float(x.get("r2"), float("-inf")),
            _as_finite_float(x.get("rmse"), float("inf")),
        ),
    )


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


def _to_csv_rows(rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    fieldnames: list[str] = []
    seen: set[str] = set()
    out_rows: list[dict[str, Any]] = []
    for row in rows:
        csv_row: dict[str, Any] = {}
        for key, value in row.items():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
            if isinstance(value, (dict, list)):
                csv_row[key] = json.dumps(value, sort_keys=True)
            else:
                csv_row[key] = value
        out_rows.append(csv_row)
    return fieldnames, out_rows


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
    validation_scheme: str,
    cv_folds: int,
    min_fold_size: int,
    min_train_size: int,
    min_samples: int,
    min_class_count: int,
    min_target_variance: float,
    sgn_min_improvement: float,
    magnitude_min_improvement: float,
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
        diagnostics = _compute_setup_diagnostics(ds.y, target_mode=target_mode)
        diagnostics["feature_count_pre_selection"] = int(len(ds.feature_columns))
        leakage_check = _leakage_check(ds.feature_columns)
        scoring_policy = _scoring_policy_for_mode(
            target_mode=target_mode,
            sgn_min_improvement=sgn_min_improvement,
            magnitude_min_improvement=magnitude_min_improvement,
        )
        sufficient, insufficiency_reasons = _assess_sufficiency(
            diagnostics,
            target_mode=target_mode,
            min_samples=min_samples,
            min_class_count=min_class_count,
            min_target_variance=min_target_variance,
        )

        selected = _select_columns(
            str(sampled["feature_selection"]),
            ds.X,
            ds.y,
            ds.feature_columns,
        )
        idx_map = {name: i for i, name in enumerate(ds.feature_columns)}
        selected_idx = [idx_map[name] for name in selected if name in idx_map]
        diagnostics["feature_count_post_selection"] = int(len(selected_idx))

        status = "insufficient_data"
        fold_summaries: list[dict[str, Any]] = []
        ann_mean: dict[str, float] = {
            "r2": 0.0,
            "mae": 0.0,
            "rmse": 0.0,
            "mape": 0.0,
            "directional_accuracy": 0.0,
        }
        ann_std: dict[str, float] = {}
        baseline: dict[str, Any] = {}
        improvement: dict[str, float] = {"score": -1e9}
        baseline_passed = False

        if not selected_idx:
            insufficiency_reasons = [
                *insufficiency_reasons,
                "feature_selection_removed_all_features",
            ]
        elif not sufficient:
            pass
        else:
            x_sel = ds.X[:, selected_idx]
            slices = _validation_slices(
                x_sel.shape[0],
                scheme=validation_scheme,
                cv_folds=cv_folds,
                min_fold_size=min_fold_size,
                min_train_size=min_train_size,
            )
            if not slices:
                insufficiency_reasons = [
                    *insufficiency_reasons,
                    "validation_folds_unavailable",
                ]
            else:
                for fold_index, (train_slice, val_slice) in enumerate(slices, start=1):
                    x_train = x_sel[train_slice]
                    y_train = ds.y[train_slice]
                    x_val = x_sel[val_slice]
                    y_val = ds.y[val_slice]
                    if y_train.shape[0] == 0 or y_val.shape[0] == 0:
                        continue

                    ann_result = train_ann_regressor(
                        x_train,
                        y_train,
                        config=cfg,
                        seed=int(seed) + int(trial) + int(fold_index),
                        X_eval=x_val,
                        y_eval=y_val,
                        use_ridge_fallback=False,
                    )
                    ann_metrics = {
                        key: _as_finite_float(value, 0.0)
                        for key, value in dict(ann_result.metrics).items()
                    }
                    baseline_metrics = _baseline_metrics_for_fold(
                        target_mode=target_mode,
                        y_train=y_train,
                        y_val=y_val,
                    )
                    fold_improvement = _improvement_from_baseline(
                        target_mode=target_mode,
                        ann_metrics=ann_metrics,
                        baseline_metrics=baseline_metrics,
                    )
                    fold_summaries.append(
                        {
                            "fold": int(fold_index),
                            "train_count": int(y_train.shape[0]),
                            "val_count": int(y_val.shape[0]),
                            "ann": ann_metrics,
                            "baseline": baseline_metrics,
                            "improvement": fold_improvement,
                        }
                    )

                if not fold_summaries:
                    insufficiency_reasons = [
                        *insufficiency_reasons,
                        "validation_folds_unavailable",
                    ]
                else:
                    ann_per_fold = [dict(x.get("ann") or {}) for x in fold_summaries]
                    ann_mean = _mean_metric_dict(ann_per_fold)
                    ann_std = _std_metric_dict(ann_per_fold)

                    baseline_selected_per_fold = [
                        str((x.get("baseline") or {}).get("selected") or "")
                        for x in fold_summaries
                    ]
                    baseline_metrics_per_fold = [
                        dict((x.get("baseline") or {}).get("selected_metrics") or {})
                        for x in fold_summaries
                    ]
                    baseline = {
                        "selected": "per_fold_best",
                        "selected_by_fold": baseline_selected_per_fold,
                        "metrics": _mean_metric_dict(baseline_metrics_per_fold),
                    }
                    improvement_per_fold = [
                        dict(x.get("improvement") or {}) for x in fold_summaries
                    ]
                    improvement = _mean_metric_dict(improvement_per_fold)

                    if str(target_mode).strip().lower() == "sgn":
                        delta = _as_finite_float(
                            improvement.get("directional_accuracy_delta"), 0.0
                        )
                        baseline_passed = bool(delta >= float(sgn_min_improvement))
                    else:
                        delta_pct = _as_finite_float(
                            improvement.get("rmse_delta_pct"), 0.0
                        )
                        baseline_passed = bool(
                            delta_pct >= float(magnitude_min_improvement)
                        )

                    status = "healthy" if baseline_passed else "fails_baseline"

        row = {
            "trial": int(trial),
            "target_mode": str(target_mode),
            "tickers": "|".join(setup_tickers),
            **sampled,
            "status": status,
            "insufficient_reasons": list(dict.fromkeys(insufficiency_reasons)),
            "features_before": int(len(ds.feature_columns)),
            "features_after": int(len(selected_idx)),
            "r2": _as_finite_float(ann_mean.get("r2"), 0.0),
            "mae": _as_finite_float(ann_mean.get("mae"), 0.0),
            "rmse": _as_finite_float(ann_mean.get("rmse"), 0.0),
            "mape": _as_finite_float(ann_mean.get("mape"), 0.0),
            "directional_accuracy": _as_finite_float(
                ann_mean.get("directional_accuracy"), 0.0
            ),
            "r2_std": _as_finite_float(ann_std.get("r2"), 0.0),
            "mae_std": _as_finite_float(ann_std.get("mae"), 0.0),
            "rmse_std": _as_finite_float(ann_std.get("rmse"), 0.0),
            "directional_accuracy_std": _as_finite_float(
                ann_std.get("directional_accuracy"), 0.0
            ),
            "baseline_name": str(baseline.get("selected") or ""),
            "baseline_rmse": _as_finite_float(
                (baseline.get("metrics") or {}).get("rmse"), 0.0
            ),
            "baseline_directional_accuracy": _as_finite_float(
                (baseline.get("metrics") or {}).get("directional_accuracy"),
                0.0,
            ),
            "improvement_vs_baseline": _as_finite_float(improvement.get("score"), -1e9),
            "improvement_directional_accuracy": _as_finite_float(
                improvement.get("directional_accuracy_delta"),
                0.0,
            ),
            "improvement_rmse_pct": _as_finite_float(
                improvement.get("rmse_delta_pct"),
                0.0,
            ),
            "baseline_passed": bool(baseline_passed),
            "validation_scheme": str(validation_scheme),
            "fold_count": int(len(fold_summaries)),
            "diagnostics": diagnostics,
            "leakage_check": leakage_check,
            "baseline": baseline,
            "improvement": improvement,
            "validation": {
                "scheme": str(validation_scheme),
                "fold_count": int(len(fold_summaries)),
                "folds": fold_summaries,
            },
            "scoring_policy": scoring_policy,
        }
        rows.append(row)
    return rows


def _select_winner(
    rows: list[dict[str, Any]],
    *,
    target_mode: str,
) -> dict[str, Any]:
    ranked = _rank(rows, target_mode=target_mode)
    healthy = [x for x in ranked if str(x.get("status") or "") == "healthy"]
    if healthy:
        return healthy[0]
    return ranked[0]


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
            validation_scheme=str(args.validation_scheme),
            cv_folds=int(args.cv_folds),
            min_fold_size=int(args.min_fold_size),
            min_train_size=int(args.min_train_size),
            min_samples=int(args.min_samples),
            min_class_count=int(args.min_class_count),
            min_target_variance=float(args.min_target_variance),
            sgn_min_improvement=float(args.sgn_min_improvement),
            magnitude_min_improvement=float(args.magnitude_min_improvement),
        )
        if not trial_rows:
            print("[ann_tune] no trials produced usable datasets")
            return 2
        ranked = _rank(trial_rows, target_mode=mode)
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
                    validation_scheme=str(args.validation_scheme),
                    cv_folds=int(args.cv_folds),
                    min_fold_size=int(args.min_fold_size),
                    min_train_size=int(args.min_train_size),
                    min_samples=int(args.min_samples),
                    min_class_count=int(args.min_class_count),
                    min_target_variance=float(args.min_target_variance),
                    sgn_min_improvement=float(args.sgn_min_improvement),
                    magnitude_min_improvement=float(args.magnitude_min_improvement),
                )
                if not trial_rows:
                    matrix_best[ticker][mode] = {
                        "status": "insufficient_data",
                        "insufficient_reasons": ["no_trials"],
                        "scoring_policy": _scoring_policy_for_mode(
                            target_mode=mode,
                            sgn_min_improvement=float(args.sgn_min_improvement),
                            magnitude_min_improvement=float(
                                args.magnitude_min_improvement
                            ),
                        ),
                    }
                    continue

                ranked = _rank(trial_rows, target_mode=mode)
                all_rows.extend(ranked)
                best = _select_winner(ranked, target_mode=mode)
                matrix_best[ticker][mode] = {
                    **_best_config_fields(best),
                    "status": str(best.get("status") or "insufficient_data"),
                    "insufficient_reasons": list(
                        best.get("insufficient_reasons") or []
                    ),
                    "r2": best["r2"],
                    "mae": best["mae"],
                    "rmse": best["rmse"],
                    "mape": best["mape"],
                    "directional_accuracy": best["directional_accuracy"],
                    "features_before": best["features_before"],
                    "features_after": best["features_after"],
                    "baseline_passed": bool(best.get("baseline_passed") or False),
                    "improvement_vs_baseline": best.get("improvement_vs_baseline", 0.0),
                    "diagnostics": dict(best.get("diagnostics") or {}),
                    "leakage_check": dict(best.get("leakage_check") or {}),
                    "baseline": dict(best.get("baseline") or {}),
                    "improvement": dict(best.get("improvement") or {}),
                    "validation": dict(best.get("validation") or {}),
                    "scoring_policy": dict(best.get("scoring_policy") or {}),
                }

        if not all_rows:
            print("[ann_tune] no trials produced usable datasets")
            return 2

    ranked_all = _rank(all_rows)
    best = _select_winner(
        ranked_all, target_mode=str(ranked_all[0].get("target_mode") or "")
    )

    out_dir = Path(args.output_dir).resolve() / f"tune_{_utc_tag()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    trials_path = out_dir / "trials.csv"
    fieldnames, csv_rows = _to_csv_rows(ranked_all)
    with trials_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

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
    healthy_count = int(
        sum(1 for row in ranked_all if str(row.get("status") or "") == "healthy")
    )

    print(f"[ann_tune] output_dir={out_dir}")
    print(f"[ann_tune] trials={len(ranked_all)}")
    print(f"[ann_tune] setups={setup_count}")
    print(f"[ann_tune] healthy_setups={healthy_count}")
    print(f"[ann_tune] best_r2={_as_finite_float(best.get('r2'), 0.0):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
