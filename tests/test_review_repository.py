from __future__ import annotations

from pathlib import Path

from src.review.models import ReviewPayloadModel
from src.review.repository import ReviewRepository


def _payload(**overrides: object) -> ReviewPayloadModel:
    base = {
        "review_date": "2026-04-02",
        "ticker": "AAPL",
        "mode": "ML + Human Review",
        "gui_state": "EDIT",
        "ai_consensus_value": 500.0,
        "ai_consensus_sgn": "+",
        "ai_consensus_strategy": "policy_selected",
        "manual_prediction_override": 501.0,
        "manual_sgn_override": "+",
        "confidence": 80,
        "justification_comment": "first save",
        "scenario_before": None,
        "scenario_after": None,
        "change_flag": False,
        "ann_magnitude": None,
        "ann_sgn": None,
        "source_context_path": "ctx.json",
        "source_snapshot_ref": "out/i_calc/*",
    }
    base.update(overrides)
    return ReviewPayloadModel(**base)


def test_repository_upsert_and_load(tmp_path: Path) -> None:
    db_path = tmp_path / "HITL_review.sqlite"
    repo = ReviewRepository(db_path)

    first = _payload()
    review_id_1 = repo.save_review_payload(first)
    assert review_id_1 > 0

    second = _payload(manual_prediction_override=503.5, justification_comment="changed")
    review_id_2 = repo.save_review_payload(second)
    assert review_id_2 == review_id_1

    loaded = repo.load_review_payload("2026-04-02", "AAPL", "ML + Human Review")
    assert loaded is not None
    assert loaded.review_id == review_id_1
    assert loaded.payload.manual_prediction_override == 503.5


def test_repository_writes_save_and_field_diff_events(tmp_path: Path) -> None:
    db_path = tmp_path / "HITL_review.sqlite"
    repo = ReviewRepository(db_path)

    repo.save_review_payload(_payload())
    repo.save_review_payload(_payload(manual_prediction_override=510.0))

    events = repo.load_audit_history("2026-04-02", "AAPL")
    event_types = [evt.event_type for evt in events.events]
    assert "SAVE" in event_types
    assert "FIELD_DIFF" in event_types
    assert any(evt.field_name == "manual_prediction_override" for evt in events.events)
