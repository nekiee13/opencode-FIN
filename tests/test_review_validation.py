from __future__ import annotations

from src.review.service import validate_review_payload


def _base_payload() -> dict[str, object]:
    return {
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
        "justification_comment": "manual adjustment",
        "scenario_before": None,
        "scenario_after": None,
        "change_flag": False,
        "ann_sgn": None,
        "ann_magnitude": None,
        "source_context_path": "out/i_calc/followup_ml/rounds/2026-04-02_r1/round_context.json",
        "source_snapshot_ref": "out/i_calc/*",
    }


def test_validate_rejects_unexpected_field() -> None:
    payload = _base_payload()
    payload["bad_field"] = 1
    out = validate_review_payload(payload)
    assert out.ok is False
    assert any("unexpected" in err.lower() for err in out.errors)


def test_validate_requires_comment_for_sgn_change() -> None:
    payload = _base_payload()
    payload["manual_sgn_override"] = "-"
    payload["justification_comment"] = ""
    out = validate_review_payload(payload)
    assert out.ok is False
    assert any("comment" in err.lower() for err in out.errors)


def test_validate_normalizes_ticker_and_mode() -> None:
    payload = _base_payload()
    payload["ticker"] = " aapl "
    payload["mode"] = "ml+hitl"
    out = validate_review_payload(payload)
    assert out.ok is True
    assert out.normalized["ticker"] == "AAPL"
    assert out.normalized["mode"] == "ML + Human Review"
