from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SchedulerKind = Literal["none", "step", "cosine", "reduce_on_plateau"]


@dataclass(frozen=True)
class SchedulerConfig:
    kind: SchedulerKind = "none"
    step_size: int = 10
    gamma: float = 0.8
    plateau_patience: int = 5
    min_learning_rate: float = 1e-5

    def __post_init__(self) -> None:
        if self.kind not in {"none", "step", "cosine", "reduce_on_plateau"}:
            raise ValueError(f"Unsupported scheduler kind: {self.kind}")
        if self.kind == "step" and self.step_size <= 0:
            raise ValueError("step_size must be > 0 for step scheduler")
        if self.gamma <= 0 or self.gamma >= 1.0:
            raise ValueError("gamma must be in (0, 1)")
        if self.plateau_patience <= 0:
            raise ValueError("plateau_patience must be > 0")
        if self.min_learning_rate <= 0:
            raise ValueError("min_learning_rate must be > 0")


@dataclass(frozen=True)
class ANNTrainingConfig:
    learning_rate: float = 1e-3
    batch_size: int = 32
    epochs: int = 300
    early_stopping_patience: int = 12
    early_stopping_min_delta: float = 1e-5

    depth: int = 2
    width: int = 32
    dropout: float = 0.10
    weight_decay: float = 1e-4

    window_length: int = 5
    lag_depth: int = 4
    forecast_horizon: int = 1

    validation_ratio: float = 0.2
    train_ratio: float = 0.8
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    def __post_init__(self) -> None:
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be > 0")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if self.epochs <= 0:
            raise ValueError("epochs must be > 0")
        if self.early_stopping_patience <= 0:
            raise ValueError("early_stopping_patience must be > 0")
        if self.depth <= 0:
            raise ValueError("depth must be > 0")
        if self.width <= 0:
            raise ValueError("width must be > 0")
        if self.dropout < 0 or self.dropout >= 1:
            raise ValueError("dropout must be in [0, 1)")
        if self.weight_decay < 0:
            raise ValueError("weight_decay must be >= 0")
        if self.window_length <= 0:
            raise ValueError("window_length must be > 0")
        if self.lag_depth < 0:
            raise ValueError("lag_depth must be >= 0")
        if self.forecast_horizon <= 0:
            raise ValueError("forecast_horizon must be > 0")
        if self.validation_ratio <= 0 or self.validation_ratio >= 0.5:
            raise ValueError("validation_ratio must be in (0, 0.5)")
        if self.train_ratio <= 0 or self.train_ratio >= 1:
            raise ValueError("train_ratio must be in (0, 1)")
        if self.early_stopping_min_delta < 0:
            raise ValueError("early_stopping_min_delta must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        scheduler = out.get("scheduler")
        if isinstance(scheduler, dict):
            out["scheduler"] = dict(scheduler)
        return out
