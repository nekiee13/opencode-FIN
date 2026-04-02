from __future__ import annotations

import json

from src.review.models import ReviewSessionModel


def build_export_payload(session: ReviewSessionModel) -> dict[str, object]:
    payload = session.payload
    return {
        "schema_version": "fin-hitl-review-v1",
        "review_id": session.review_id,
        "round_id": payload.round_id,
        "review_date": payload.review_date,
        "ticker": payload.ticker,
        "mode": payload.mode,
        "gui_state": payload.gui_state,
        "ai_consensus": {
            "value": payload.ai_consensus_value,
            "sgn": payload.ai_consensus_sgn,
            "strategy": payload.ai_consensus_strategy,
        },
        "human_review": {
            "manual_prediction_override": payload.manual_prediction_override,
            "manual_sgn_override": payload.manual_sgn_override,
            "confidence": payload.confidence,
            "justification_comment": payload.justification_comment,
        },
        "scenario": {
            "before": payload.scenario_before,
            "after": payload.scenario_after,
            "change_flag": payload.change_flag,
        },
        "ann": {
            "sgn": payload.ann_sgn,
            "magnitude": payload.ann_magnitude,
        },
        "source_refs": {
            "context_json": payload.source_context_path,
            "snapshot_ref": payload.source_snapshot_ref,
        },
        "timestamps": {
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        },
    }


def export_payload_json_text(session: ReviewSessionModel) -> str:
    return json.dumps(
        build_export_payload(session),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
