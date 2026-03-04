from __future__ import annotations

import pandas as pd
import pytest

from src.followup_ml.draft import _finalize_override_policy, _render_round_markdown


def test_render_round_markdown_override_notice() -> None:
    dayn = pd.DataFrame(columns=["ticker"])
    metrics = pd.DataFrame(columns=["ticker", "available_models", "day3_spread"])

    md = _render_round_markdown(
        round_id="26-1-11",
        round_state="FINAL_TPLUS3",
        generated_at="2026-02-28 00:00:00",
        fh=3,
        dayn_df=dayn,
        metrics_df=metrics,
        run_mode="lookup_override_test",
        lookup_date_override="2026-02-17",
    )

    assert "Run mode: `lookup_override_test`" in md
    assert "lookup_date=2026-02-17" in md
    assert "not strict production" in md


def test_finalize_override_policy_blocks_without_ack() -> None:
    with pytest.raises(ValueError, match="blocked by production policy"):
        _finalize_override_policy(
            actual_lookup_date="2026-02-17",
            allow_lookup_override=False,
            override_reason=None,
            override_ticket=None,
            override_approver=None,
        )


def test_finalize_override_policy_requires_ack_fields() -> None:
    with pytest.raises(ValueError, match="Missing: reason, ticket, approver"):
        _finalize_override_policy(
            actual_lookup_date="2026-02-17",
            allow_lookup_override=True,
            override_reason="",
            override_ticket="",
            override_approver="",
        )


def test_finalize_override_policy_allows_with_ack() -> None:
    lookup_override, run_mode, ack = _finalize_override_policy(
        actual_lookup_date="2026-02-17",
        allow_lookup_override=True,
        override_reason="benchmark backtest",
        override_ticket="CHG-123",
        override_approver="ops_lead",
    )

    assert lookup_override == "2026-02-17"
    assert run_mode == "lookup_override_test"
    assert ack["reason"] == "benchmark backtest"
    assert ack["ticket"] == "CHG-123"
    assert ack["approver"] == "ops_lead"
