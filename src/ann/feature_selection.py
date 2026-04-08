from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _ridge_importance(X: np.ndarray, y: np.ndarray, alpha: float = 1e-6) -> np.ndarray:
    x = np.asarray(X, dtype=float)
    t = np.asarray(y, dtype=float).reshape(-1)
    if x.ndim != 2 or x.shape[0] == 0:
        return np.zeros((x.shape[1] if x.ndim == 2 else 0,), dtype=float)

    xtx = x.T @ x
    reg = alpha * np.eye(xtx.shape[0], dtype=float)
    xty = x.T @ t
    beta = np.linalg.pinv(xtx + reg) @ xty
    return np.abs(beta)


def correlation_filter(
    X: np.ndarray,
    columns: list[str],
    *,
    threshold: float,
) -> list[str]:
    if threshold <= 0 or threshold >= 1:
        raise ValueError("threshold must be in (0, 1)")

    x = np.asarray(X, dtype=float)
    if x.ndim != 2:
        raise ValueError("X must be 2D")
    if x.shape[1] != len(columns):
        raise ValueError("columns length does not match X columns")
    if x.shape[1] <= 1:
        return list(columns)

    corr = np.corrcoef(x, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)
    keep = [True] * x.shape[1]
    for i in range(x.shape[1]):
        if not keep[i]:
            continue
        for j in range(i + 1, x.shape[1]):
            if keep[j] and abs(float(corr[i, j])) >= threshold:
                keep[j] = False
    return [name for name, flag in zip(columns, keep) if flag]


def model_importance_prune(
    X: np.ndarray,
    y: np.ndarray,
    columns: list[str],
    *,
    keep_ratio: float,
) -> list[str]:
    if keep_ratio <= 0 or keep_ratio > 1:
        raise ValueError("keep_ratio must be in (0, 1]")

    x = np.asarray(X, dtype=float)
    if x.ndim != 2:
        raise ValueError("X must be 2D")
    if x.shape[1] != len(columns):
        raise ValueError("columns length mismatch")
    if x.shape[1] == 0:
        return []

    keep_count = max(1, int(round(float(x.shape[1]) * keep_ratio)))
    importances = _ridge_importance(x, np.asarray(y, dtype=float))
    ranked_idx = np.argsort(importances)[::-1][:keep_count]
    selected = sorted([int(i) for i in ranked_idx])
    return [columns[i] for i in selected]


@dataclass(frozen=True)
class RFEResult:
    selected_columns: list[str]
    history: list[dict[str, object]]


def recursive_feature_elimination(
    X: np.ndarray,
    y: np.ndarray,
    columns: list[str],
    *,
    min_features: int,
    drop_count_per_round: int,
) -> RFEResult:
    x = np.asarray(X, dtype=float)
    if x.ndim != 2:
        raise ValueError("X must be 2D")
    if x.shape[1] != len(columns):
        raise ValueError("columns length mismatch")
    if min_features <= 0:
        raise ValueError("min_features must be > 0")
    if drop_count_per_round <= 0:
        raise ValueError("drop_count_per_round must be > 0")

    selected = list(range(x.shape[1]))
    history: list[dict[str, object]] = []
    round_no = 0

    while len(selected) > min_features:
        round_no += 1
        x_sel = x[:, selected]
        importances = _ridge_importance(x_sel, np.asarray(y, dtype=float))
        order = np.argsort(importances)
        drop_n = min(drop_count_per_round, len(selected) - min_features)
        drop_local = [int(i) for i in order[:drop_n]]
        dropped_global = [selected[i] for i in drop_local]
        dropped_names = [columns[i] for i in dropped_global]

        selected = [idx for idx in selected if idx not in dropped_global]
        history.append(
            {
                "round": round_no,
                "dropped": dropped_names,
                "remaining": [columns[i] for i in selected],
            }
        )

    return RFEResult(
        selected_columns=[columns[i] for i in selected],
        history=history,
    )
