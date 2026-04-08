from __future__ import annotations

import numpy as np

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
