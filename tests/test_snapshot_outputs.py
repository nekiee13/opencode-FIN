# ------------------------
# tests/test_snapshot_outputs.py
# ------------------------
"""
Snapshot-style tests for FIN outputs.

Scope
-----
- Pivot points: deterministic markdown formatting from deterministic OHLC.
- SVL structural indicators: markdown export + metrics CSV schema (deterministic, synthetic OHLCV).

Notes
-----
- No external snapshot plugin dependency is required.
- Snapshots are embedded as expected strings (golden text).
- The SVL snapshot is constructed from the returned context object to avoid brittle
  hardcoding of floating values while still enforcing the export format.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd


def _make_bday_ohlcv_sine(
    n: int,
    *,
    start: str = "2024-01-02",
    seed: int = 7,
) -> pd.DataFrame:
    """
    Deterministic OHLCV generator intended for stable Hurst + Trend10D behavior.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start=start, periods=n, freq="B")

    t = np.arange(n, dtype=float)
    close = 100.0 + 0.05 * t + 2.0 * np.sin(2.0 * np.pi * t / 30.0) + rng.normal(0.0, 0.15, size=n)
    close = np.maximum(close, 1.0)

    open_ = close + rng.normal(0.0, 0.10, size=n)
    high = np.maximum(open_, close) + np.abs(rng.normal(0.20, 0.05, size=n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0.20, 0.05, size=n))
    vol = rng.integers(1_000_000, 2_000_000, size=n)

    return pd.DataFrame(
        {
            "Open": open_.astype(float),
            "High": high.astype(float),
            "Low": low.astype(float),
            "Close": close.astype(float),
            "Volume": vol.astype(float),
        },
        index=idx,
    )


def _norm_ws(s: str) -> str:
    """
    Normalize whitespace for stable comparisons:
    - strip ends
    - collapse internal whitespace per line
    """
    return "\n".join(" ".join(line.split()) for line in s.strip().splitlines())


def _fmt2(x: Any) -> str:
    """
    Safe float formatting for snapshot strings.

    Avoids Pylance complaints by ensuring the argument to float() is typed as Any.
    """
    try:
        if x is None or pd.isna(x):
            return "NA"

        # Fast-path numeric-ish values
        if isinstance(x, (int, float, np.integer, np.floating)):
            v = float(x)
        elif isinstance(x, str):
            v = float(x)
        else:
            # Last resort: attempt float conversion on unknown objects
            v = float(cast(Any, x))

        if not np.isfinite(v):
            return "NA"
        return f"{v:.2f}"
    except Exception:
        return "NA"


def test_pivot_points_markdown_snapshot() -> None:
    from src.utils.pivots import calculate_latest_pivot_points, format_pivot_table

    idx = pd.bdate_range("2024-06-03", periods=2, freq="B")

    # Previous day supplies H/L/C, current day supplies O for Woodie/DeMark branches.
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [110.0, 111.0],
            "Low": [90.0, 95.0],
            "Close": [105.0, 106.0],
            "Volume": [1_000_000.0, 1_100_000.0],
        },
        index=idx,
    )

    res = calculate_latest_pivot_points(df)
    assert res is not None

    md = format_pivot_table(res.pivot_data, ticker="TEST", date=res.asof_date, decimals=3)

    # Snapshot expectation: stable because inputs are exact and formatting is fixed.
    # Expected values are aligned to the implemented formulas in src.utils.pivots:
    # - Classic S1 = 2P - H, R1 = 2P - L, S2 = P - (H-L), R2 = P + (H-L), etc.
    # - Camarilla uses C ± (H-L)*1.1/{12,6,4}.
    # - Woodie's uses P = (H + L + 2O)/4 with S2/R2 = P ± (H-L).
    # - DeMark's uses branch decision on prev close vs current open.
    expected = "\n".join(
        [
            "#### Pivot Points for TEST (2024-06-04):",
            "| Method      | S3    | S2    | S1    | Pivot Points | R1    | R2    | R3    |",
            "|-------------|-------|-------|-------|--------------|-------|-------|-------|",
            "| Classic     | 61.667 | 81.667 | 93.333 | 101.667 | 113.333 | 121.667 | 141.667 |",
            "| Fibonacci   | 81.667 | 89.307 | 94.027 | 101.667 | 109.307 | 114.027 | 121.667 |",
            "| Camarilla   | 99.500 | 101.333 | 103.167 | 101.667 | 106.833 | 108.667 | 110.500 |",
            "| Woodie's    | - | 80.500 | 91.000 | 100.500 | 111.000 | 120.500 | - |",
            "| DeMark's    | - | - | 97.500 | 103.750 | 117.500 | - | - |",
        ]
    )

    assert _norm_ws(md) == _norm_ws(expected)


def test_structural_context_markdown_snapshot() -> None:
    from src.structural.svl_indicators import (
        compute_structural_context_for_ticker,
        export_structural_context_markdown,
    )

    df = _make_bday_ohlcv_sine(n=160, start="2024-01-02", seed=7).reset_index()
    df = df.rename(columns={"index": "Date"})

    ctx = compute_structural_context_for_ticker(
        ticker="TEST",
        df_ohlcv_raw=df,
        data_source="CSV:SYNTHETIC",
        computed_on="2026-01-26 12:00",
        method_notes="UNITTEST: synthetic OHLCV",
    )

    md = export_structural_context_markdown([ctx], global_asof_date=ctx.asof_date)

    # Build the expected snapshot using ctx fields to avoid brittle hardcoding of floats.
    # This still enforces the exact export structure (headings/labels/order).
    method_notes_val = cast(str, ctx.provenance.get("method_notes", "") or "")
    method_notes_safe = method_notes_val.replace('"', "'")

    will_note_val = cast(str, ctx.williams.note or "")
    will_note_safe = will_note_val.replace('"', "'")

    h20_list_str = ", ".join("NA" if v is None else f"{float(v):.2f}" for v in ctx.hurst.h20_last10)
    lvl_str = "NA" if ctx.williams.level is None else f"{float(ctx.williams.level):.2f}"

    expected = "\n".join(
        [
            "STRUCTURAL_CONTEXT (Computed from internal OHLCV; no web citations)",
            "",
            f"As-of (last close): {ctx.asof_date}",
            "Data source: CSV:SYNTHETIC",
            "Lookbacks: H20/H60/H120; Williams fractals (5-bar); H20 mini-history = last 10 business days",
            "Trend definition: Trend10D computed from Close over last 10 business days (UP if >= +1%, DOWN if <= -1%, else FLAT)",
            "",
            "[TEST]",
            "Hurst:",
            f"  H20_current: {_fmt2(ctx.hurst.h20_current)}",
            f"  H60_current: {_fmt2(ctx.hurst.h60_current)}",
            f"  H120_current: {_fmt2(ctx.hurst.h120_current)}",
            f"  Regime_current: {ctx.hurst.regime_current}",
            f"  H20_last10: [{h20_list_str}]",
            f"  RegimeChange_last10: {ctx.hurst.regime_change_last10}",
            f'  RegimeChange_note: "{ctx.hurst.regime_change_note}"',
            f"Trend10D: {ctx.trend10d}",
            "WilliamsFractals:",
            f"  Signal_last5: {ctx.williams.signal_last5}",
            f"  Level: {lvl_str}",
            f'  Note: "{will_note_safe}"',
            "Provenance:",
            "  computed_on: 2026-01-26 12:00",
            f'  method_notes: "{method_notes_safe}"',
            "",
        ]
    )

    assert md == expected


def test_structural_metrics_csv_snapshot_schema() -> None:
    from src.structural.svl_indicators import compute_structural_context_for_ticker, export_metrics_csv

    df = _make_bday_ohlcv_sine(n=160, start="2024-01-02", seed=7).reset_index()
    df = df.rename(columns={"index": "Date"})

    ctx = compute_structural_context_for_ticker(
        ticker="TEST",
        df_ohlcv_raw=df,
        data_source="CSV:SYNTHETIC",
        computed_on="2026-01-26 12:00",
        method_notes="UNITTEST: synthetic OHLCV",
    )

    out = export_metrics_csv([ctx])
    assert isinstance(out, pd.DataFrame)
    assert len(out) == 1

    expected_cols = [
        "Ticker",
        "Ticker_AsOf",
        "H20",
        "H60",
        "H120",
        "Regime_current",
        "RegimeChange_last10",
        "RegimeChange_note",
        "Trend10D",
        "Williams_Signal_last5",
        "Williams_Level",
        "Computed_on",
        "Data_source",
    ]
    assert list(out.columns) == expected_cols

    # Avoid ambiguous truth checks for pandas objects; use explicit scalar extraction.
    assert str(out.loc[0, "Ticker"]) == "TEST"
    assert str(out.loc[0, "Ticker_AsOf"]) == ctx.asof_date
    assert str(out.loc[0, "Data_source"]) == "CSV:SYNTHETIC"


def test_structural_module_import_smoke() -> None:
    import importlib

    mod = importlib.import_module("src.structural.svl_indicators")
    assert mod is not None


def test_pivots_module_import_smoke() -> None:
    import importlib

    mod = importlib.import_module("src.utils.pivots")
    assert mod is not None
