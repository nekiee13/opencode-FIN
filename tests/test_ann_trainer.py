from __future__ import annotations

import numpy as np
import warnings

from src.ann.config import ANNTrainingConfig, SchedulerConfig
from src.ann.metrics import regression_metrics
from src.ann.trainer import train_ann_regressor


def test_train_ann_regressor_returns_metrics_with_r2() -> None:
    rng = np.random.default_rng(123)
    X = rng.normal(size=(120, 4))
    y = (1.8 * X[:, 0]) + (-0.9 * X[:, 1]) + (0.5 * X[:, 2])

    cfg = ANNTrainingConfig(
        learning_rate=0.01,
        batch_size=16,
        epochs=80,
        early_stopping_patience=10,
        depth=2,
        width=16,
        dropout=0.05,
        weight_decay=0.0001,
        scheduler=SchedulerConfig(kind="step", step_size=20, gamma=0.8),
    )
    result = train_ann_regressor(X, y, config=cfg, seed=42)

    assert "r2" in result.metrics
    assert result.metrics["r2"] > 0.7
    assert result.best_epoch >= 1
    assert result.best_epoch <= cfg.epochs


def test_regression_metrics_include_r2() -> None:
    y_true = np.array([1.0, 2.0, 3.0], dtype=float)
    y_pred = np.array([1.1, 2.1, 2.9], dtype=float)
    out = regression_metrics(y_true, y_pred)
    assert set(["r2", "mae", "rmse", "mape", "directional_accuracy"]).issubset(
        out.keys()
    )


def test_train_ann_regressor_suppresses_runtime_overflow_warnings() -> None:
    rng = np.random.default_rng(99)
    X = rng.normal(size=(100, 12))
    y = rng.choice([-1.0, 1.0], size=100).astype(float)

    cfg = ANNTrainingConfig(
        learning_rate=0.05,
        batch_size=16,
        epochs=60,
        early_stopping_patience=8,
        depth=3,
        width=64,
        dropout=0.2,
        weight_decay=0.001,
    )

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        out = train_ann_regressor(X, y, config=cfg, seed=11)

    runtime_warns = [w for w in seen if issubclass(w.category, RuntimeWarning)]
    assert not runtime_warns
    assert np.isfinite(out.metrics["r2"])


def test_train_ann_regressor_supports_explicit_eval_split() -> None:
    rng = np.random.default_rng(2026)
    X = rng.normal(size=(60, 5))
    y = (2.0 * X[:, 0]) - (0.5 * X[:, 1]) + rng.normal(scale=0.05, size=60)

    X_train = X[:40]
    y_train = y[:40]
    X_eval = X[40:]
    y_eval = y[40:]

    cfg = ANNTrainingConfig(
        learning_rate=0.01,
        batch_size=8,
        epochs=40,
        early_stopping_patience=6,
        depth=1,
        width=16,
        dropout=0.0,
        weight_decay=0.0,
    )
    out = train_ann_regressor(
        X_train,
        y_train,
        config=cfg,
        seed=7,
        X_eval=X_eval,
        y_eval=y_eval,
        use_ridge_fallback=False,
    )

    assert np.isfinite(out.metrics["r2"])
    assert np.isfinite(out.metrics["mae"])
    assert np.isfinite(out.metrics["rmse"])
