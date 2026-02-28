from __future__ import annotations

import pandas as pd

from src.followup_ml.draft import _render_round_markdown


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
