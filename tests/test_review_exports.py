from __future__ import annotations

import json
from pathlib import Path

from src.review.models import ReviewPayloadModel
from src.review.repository import ReviewRepository
from src.review.service import export_review_payload


def test_export_review_payload_is_deterministic_json(tmp_path: Path) -> None:
    db_path = tmp_path / "HITL_review.sqlite"
    repo = ReviewRepository(db_path)

    review_id = repo.save_review_payload(
        ReviewPayloadModel(
            review_date="2026-04-02",
            ticker="AAPL",
            mode="ML + Human Review",
            gui_state="EDIT",
            ai_consensus_value=500.0,
            ai_consensus_sgn="+",
            ai_consensus_strategy="policy_selected",
            manual_prediction_override=501.0,
            manual_sgn_override="+",
            confidence=80,
            justification_comment="export check",
            scenario_before=None,
            scenario_after=None,
            change_flag=False,
            ann_magnitude=0.7,
            ann_sgn="+",
            source_context_path="ctx.json",
            source_snapshot_ref="out/i_calc/*",
        )
    )

    json_text_a = export_review_payload(repo, review_id, "json", "full")
    json_text_b = export_review_payload(repo, review_id, "json", "full")
    assert json_text_a == json_text_b

    payload = json.loads(json_text_a)
    assert payload["schema_version"] == "fin-hitl-review-v1"
    assert payload["review_id"] == review_id
    assert payload["ticker"] == "AAPL"
    assert payload["ai_consensus"]["strategy"] == "policy_selected"
