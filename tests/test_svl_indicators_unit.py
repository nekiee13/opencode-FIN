from __future__ import annotations

import pandas as pd


def test_hurst_regime_threshold_boundaries() -> None:
    from src.structural.svl_indicators import hurst_regime

    assert hurst_regime(0.56) == "PERSISTENT"
    assert hurst_regime(0.55) == "RANDOM"
    assert hurst_regime(0.45) == "RANDOM"
    assert hurst_regime(0.44) == "MEAN_REVERT"
    assert hurst_regime(None) == "UNKNOWN"


def test_trend10d_boundaries() -> None:
    from src.structural.svl_indicators import compute_trend10d

    up = pd.Series([100.0] * 9 + [101.0])
    down = pd.Series([100.0] * 9 + [99.0])
    flat = pd.Series([100.0] * 9 + [100.5])

    assert compute_trend10d(up)[0] == "UP"
    assert compute_trend10d(down)[0] == "DOWN"
    assert compute_trend10d(flat)[0] == "FLAT"


def test_williams_fractal_confirmation_and_scan_window() -> None:
    from src.structural.svl_indicators import (
        active_fractal_last5,
        compute_williams_fractals,
    )

    n = 12
    idx = pd.date_range("2026-01-01", periods=n, freq="D")

    high = pd.Series(
        [11.0, 11.2, 11.1, 11.0, 11.3, 11.2, 11.1, 11.2, 11.1, 11.0, 11.2, 11.3],
        index=idx,
    )
    low = pd.Series(
        [10.0, 10.1, 10.2, 10.1, 10.0, 9.9, 9.8, 9.7, 9.6, 9.0, 9.7, 9.8], index=idx
    )

    fr = compute_williams_fractals(high, low)
    assert bool(fr.loc[n - 1, "bull_fractal"]) is False
    assert bool(fr.loc[n - 2, "bull_fractal"]) is False
    assert bool(fr.loc[n - 1, "bear_fractal"]) is False
    assert bool(fr.loc[n - 2, "bear_fractal"]) is False

    df = pd.DataFrame({"High": high, "Low": low, "Close": (high + low) / 2.0})
    sig = active_fractal_last5(df)

    assert sig.signal_last5 == "BULLISH"
    assert sig.level is not None


def test_regime_change_last10_detection() -> None:
    from src.structural.svl_indicators import regime_change_last10

    dates = list(pd.bdate_range("2026-01-05", periods=10, freq="B"))
    h20_last10 = [0.61, 0.60, None, 0.58, 0.50, 0.49, 0.44, 0.43, None, 0.42]

    flag, note = regime_change_last10(h20_last10, dates)
    assert flag == "YES"
    assert "RANDOM" in note
    assert "MEAN_REVERT" in note


def test_structural_context_degrades_on_invalid_input() -> None:
    from src.structural.svl_indicators import compute_structural_context_for_ticker

    bad_df = pd.DataFrame({"foo": [1, 2, 3]})
    ctx = compute_structural_context_for_ticker(
        ticker="BAD",
        df_ohlcv_raw=bad_df,
        data_source="UNITTEST",
        computed_on="2026-02-16 12:00",
        method_notes="unit",
    )

    assert ctx.ticker == "BAD"
    assert ctx.hurst.regime_current == "UNKNOWN"
    assert ctx.trend10d == "FLAT"
