from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class GuiRoundStateModel:
    raw_round_state: str
    gui_state: str
    editable: bool
    reason: str


@dataclass(frozen=True)
class ModelComparisonRowModel:
    model_name: str
    prediction_value: float | None
    lower_bound: float | None
    upper_bound: float | None
    weight: float | None
    status: str
    selected: bool
    notes: str


@dataclass(frozen=True)
class ConsensusResultModel:
    ticker: str
    review_date: str
    consensus_value: float | None
    consensus_sgn: str | None
    strategy_name: str
    contributing_models: tuple[str, ...]
    excluded_models: tuple[str, ...]
    source_artifacts: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class ScenarioResultModel:
    scenario_label: str | None
    source_inputs: Mapping[str, Any]
    thresholds_used: Mapping[str, Any]
    reason_codes: tuple[str, ...]
    changed_from_prior: bool


@dataclass(frozen=True)
class ReviewPayloadModel:
    review_date: str
    ticker: str
    mode: str
    gui_state: str
    ai_consensus_value: float | None
    ai_consensus_sgn: str | None
    ai_consensus_strategy: str
    manual_prediction_override: float | None
    manual_sgn_override: str | None
    confidence: int | None
    justification_comment: str | None
    scenario_before: str | None
    scenario_after: str | None
    change_flag: bool
    ann_magnitude: float | None
    ann_sgn: str | None
    source_context_path: str | None
    source_snapshot_ref: str | None
    round_id: str | None = None


@dataclass(frozen=True)
class ReviewSessionModel:
    review_id: int
    payload: ReviewPayloadModel
    created_at: str
    updated_at: str
    save_status: str


@dataclass(frozen=True)
class ReviewEventModel:
    event_id: int
    review_id: int
    event_type: str
    field_name: str | None
    old_value: str | None
    new_value: str | None
    event_status: str
    error_text: str | None
    created_at: str


@dataclass(frozen=True)
class AuditHistoryModel:
    review_date: str
    ticker: str
    events: tuple[ReviewEventModel, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ValidationResultModel:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    normalized: Mapping[str, Any]


@dataclass(frozen=True)
class ANNSnapshotModel:
    review_date: str
    ticker: str
    ann_sgn: str | None
    ann_magnitude: float | None
    source_label: str | None
    ingested_at: str | None
    stale_warning: bool
