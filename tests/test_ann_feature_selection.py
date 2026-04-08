from __future__ import annotations

import numpy as np
import warnings

from src.ann.feature_selection import (
    correlation_filter,
    model_importance_prune,
    recursive_feature_elimination,
)


def test_correlation_filter_drops_highly_correlated_columns() -> None:
    X = np.array(
        [
            [1.0, 2.0, 10.0],
            [2.0, 4.0, 11.0],
            [3.0, 6.0, 9.0],
            [4.0, 8.0, 12.0],
        ],
        dtype=float,
    )
    cols = ["a", "b", "c"]
    kept = correlation_filter(X, cols, threshold=0.95)
    assert "a" in kept
    assert "c" in kept
    assert len(kept) == 2


def test_model_importance_prune_keeps_stronger_signal() -> None:
    x1 = np.linspace(0, 1, 50)
    x2 = np.random.default_rng(42).normal(0, 0.01, size=50)
    y = 5 * x1 + 0.01 * x2
    X = np.column_stack([x1, x2])
    kept = model_importance_prune(X, y, ["x1", "x2"], keep_ratio=0.5)
    assert kept == ["x1"]


def test_recursive_feature_elimination_reaches_min_features() -> None:
    rng = np.random.default_rng(7)
    X = rng.normal(size=(80, 6))
    y = 3.0 * X[:, 0] - 2.0 * X[:, 1] + rng.normal(scale=0.1, size=80)
    cols = [f"f{i}" for i in range(6)]
    out = recursive_feature_elimination(
        X,
        y,
        cols,
        min_features=2,
        drop_count_per_round=2,
    )
    assert len(out.selected_columns) == 2
    assert out.history


def test_correlation_filter_constant_columns_no_runtime_warning() -> None:
    X = np.array(
        [
            [1.0, 1.0, 4.0],
            [1.0, 1.0, 5.0],
            [1.0, 1.0, 6.0],
            [1.0, 1.0, 7.0],
        ],
        dtype=float,
    )
    cols = ["c1", "c2", "c3"]
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        kept = correlation_filter(X, cols, threshold=0.95)
    assert kept
    assert not [w for w in seen if issubclass(w.category, RuntimeWarning)]
