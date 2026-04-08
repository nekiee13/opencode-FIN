from __future__ import annotations

import pytest

from src.ann.config import ANNTrainingConfig, SchedulerConfig


def test_ann_training_config_defaults_are_valid() -> None:
    cfg = ANNTrainingConfig()
    assert cfg.learning_rate > 0
    assert cfg.batch_size > 0
    assert cfg.epochs > 0
    assert cfg.window_length > 0
    assert cfg.lag_depth >= 0


def test_ann_training_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        ANNTrainingConfig(learning_rate=0)

    with pytest.raises(ValueError):
        ANNTrainingConfig(batch_size=0)

    with pytest.raises(ValueError):
        ANNTrainingConfig(dropout=1.2)


def test_scheduler_config_step_requires_step_size() -> None:
    with pytest.raises(ValueError):
        SchedulerConfig(kind="step", gamma=0.5, step_size=0)

    cfg = SchedulerConfig(kind="step", gamma=0.7, step_size=5)
    assert cfg.kind == "step"
