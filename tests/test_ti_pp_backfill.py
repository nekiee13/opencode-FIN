from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ui.services import ti_pp_backfill


def test_runtime_ticker_for_maps_spx_to_gspc() -> None:
    assert ti_pp_backfill.runtime_ticker_for("SPX") == "GSPC"
    assert ti_pp_backfill.runtime_ticker_for("TNX") == "TNX"


def test_backfill_ti_pp_for_date_runs_replay_and_persists_logical_ticker(
    monkeypatch,
) -> None:
    calls: dict[str, object] = {}
    ti_saved: list[tuple[str, str]] = []
    pp_saved: list[tuple[str, str]] = []

    idx = pd.to_datetime(["2025-08-18", "2025-08-19"])
    enriched = pd.DataFrame(
        {
            "Open": [1.0, 1.1],
            "High": [1.2, 1.3],
            "Low": [0.9, 1.0],
            "Close": [1.05, 1.15],
            "RSI (14)": [50.0, 51.0],
            "Stochastic %K": [40.0, 42.0],
            "ATR (14)": [0.2, 0.21],
            "ADX (14)": [20.0, 21.0],
            "CCI (14)": [10.0, 11.0],
            "Williams %R": [-40.0, -39.0],
            "Ultimate Oscillator": [45.0, 46.0],
            "ROC (10)": [0.4, 0.5],
            "BullBear Power": [0.01, 0.02],
            "MA50": [1.0, 1.01],
            "MA200": [0.95, 0.96],
        },
        index=idx,
    )

    def _fake_run_external_ti_calculator(
        ticker: str,
        progress_callback=None,
        *,
        history_mode: str | None = None,
        as_of_date: str | None = None,
    ) -> pd.DataFrame:
        _ = progress_callback
        calls["runtime_ticker"] = ticker
        calls["history_mode"] = history_mode
        calls["as_of_date"] = as_of_date
        return enriched

    def _fake_persist_ti_snapshot(
        *,
        ticker: str,
        asof_date,
        latest_indicators,
        pivot_data,
    ) -> Path:
        _ = latest_indicators
        _ = pivot_data
        ti_saved.append((str(ticker), pd.Timestamp(asof_date).strftime("%Y-%m-%d")))
        return Path("/tmp/TI.csv")

    def _fake_persist_pp_snapshot(*, ticker: str, asof_date, pivot_data) -> Path:
        _ = pivot_data
        pp_saved.append((str(ticker), pd.Timestamp(asof_date).strftime("%Y-%m-%d")))
        return Path("/tmp/PP.csv")

    monkeypatch.setattr(
        ti_pp_backfill.models_api,
        "run_external_ti_calculator",
        _fake_run_external_ti_calculator,
    )
    monkeypatch.setattr(
        ti_pp_backfill,
        "calculate_latest_pivot_points",
        lambda df: {"Classic": {"Pivot": float(df["Close"].iloc[-1])}},
    )
    monkeypatch.setattr(
        ti_pp_backfill,
        "persist_ti_snapshot",
        _fake_persist_ti_snapshot,
    )
    monkeypatch.setattr(
        ti_pp_backfill,
        "persist_pp_snapshot",
        _fake_persist_pp_snapshot,
    )

    out = ti_pp_backfill.backfill_ti_pp_for_date(
        selected_date="2025-08-19",
        tickers=["SPX"],
        stop_on_error=True,
    )

    assert out["status"] == "success"
    assert calls["runtime_ticker"] == "GSPC"
    assert calls["history_mode"] == "replay"
    assert calls["as_of_date"] == "2025-08-19"
    assert ti_saved == [("SPX", "2025-08-19")]
    assert pp_saved == [("SPX", "2025-08-19")]
