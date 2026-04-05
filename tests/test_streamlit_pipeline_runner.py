from __future__ import annotations

from src.ui.services.pipeline_runner import TICKER_ORDER, build_pipeline_commands


def test_build_pipeline_commands_single_ticker_replay_mode() -> None:
    commands = build_pipeline_commands(
        selected_date="2026-03-24",
        selected_ticker="TNX",
    )
    assert len(commands) == 5
    core = commands[:3]
    for spec in core:
        joined = " ".join(spec.command)
        assert "--history-mode" in joined
        assert "replay" in joined
        assert "--as-of-date" in joined
        assert "2026-03-24" in joined


def test_build_pipeline_commands_all_tickers_in_sequence() -> None:
    commands = build_pipeline_commands(
        selected_date="2026-03-24",
        selected_ticker="ALL",
    )
    core = [x for x in commands if x.category == "core"]
    assert len(core) == len(TICKER_ORDER) * 3
    assert core[0].ticker == TICKER_ORDER[0]
    assert core[-1].ticker == TICKER_ORDER[-1]
