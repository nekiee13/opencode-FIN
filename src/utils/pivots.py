# ------------------------
# src/utils/pivots.py
# ------------------------

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, cast

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------

LevelMap = Dict[str, float]
PivotByMethod = Dict[str, LevelMap]


@dataclass(frozen=True)
class PivotCalcResult:
    """
    Convenience typed wrapper around pivot computations.

    pivot_data:
        Method -> level name -> value
    asof_date:
        Date of the "current" bar (the day pivot levels are produced for).
    based_on_date:
        Date of the "previous" bar that supplied H/L/C.
    """

    pivot_data: PivotByMethod
    asof_date: pd.Timestamp
    based_on_date: pd.Timestamp


# ----------------------------------------------------------------------
# Core pivot calculations
# ----------------------------------------------------------------------


def _validate_ohlc(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty:
        return "Empty input."
    if len(df) < 2:
        return "Insufficient rows (need >= 2)."
    if not isinstance(df.index, pd.DatetimeIndex):
        return "Index must be a DatetimeIndex."
    required = ["Open", "High", "Low", "Close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return f"Missing required columns: {missing}."
    return None


def calculate_latest_pivot_points(data: pd.DataFrame) -> Optional[PivotCalcResult]:
    """
    Calculate daily pivot points using five methodologies (legacy-compatible).

    Uses:
      - Previous day's High/Low/Close (H, L, C)
      - Current day's Open (O) for Woodie's + DeMark's X logic (legacy behavior)

    Returns
    -------
    PivotCalcResult | None
    """
    err = _validate_ohlc(data)
    if err:
        log.warning("Pivot Calc: %s", err)
        return None

    try:
        df = data.copy()
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()

        # Static typing: _validate_ohlc enforces DatetimeIndex at runtime, but Pylance
        # does not narrow df.index automatically; cast is required.
        idx = cast(pd.DatetimeIndex, df.index)

        # Current day = last row; Previous day = second last row
        last_day = df.iloc[-1]
        prev_day = df.iloc[-2]

        H = float(prev_day["High"])
        L = float(prev_day["Low"])
        C = float(prev_day["Close"])
        open_curr = float(last_day["Open"])

        if any(pd.isna([H, L, C, open_curr])):
            log.warning(
                "Pivot Calc: NaN values found in required OHLC for calculation."
            )
            return None

        rng = H - L
        if rng <= 0:
            log.warning("Pivot Calc: Previous day's High (%.6f) <= Low (%.6f).", H, L)
            if rng < 0:
                rng = 0.0

        pivots: PivotByMethod = {}

        # ----------------------
        # Classic
        # ----------------------
        P_classic = (H + L + C) / 3.0
        pivots["Classic"] = {
            "S3": P_classic - 2.0 * rng,
            "S2": P_classic - 1.0 * rng,
            "S1": 2.0 * P_classic - H,
            "Pivot": P_classic,
            "R1": 2.0 * P_classic - L,
            "R2": P_classic + 1.0 * rng,
            "R3": P_classic + 2.0 * rng,
        }

        # ----------------------
        # Fibonacci
        # ----------------------
        P_fib = (H + L + C) / 3.0
        pivots["Fibonacci"] = {
            "S3": P_fib - 1.000 * rng,
            "S2": P_fib - 0.618 * rng,
            "S1": P_fib - 0.382 * rng,
            "Pivot": P_fib,
            "R1": P_fib + 0.382 * rng,
            "R2": P_fib + 0.618 * rng,
            "R3": P_fib + 1.000 * rng,
        }

        # ----------------------
        # Camarilla
        # ----------------------
        pivots["Camarilla"] = {
            "S3": C - rng * 1.1 / 4.0,
            "S2": C - rng * 1.1 / 6.0,
            "S1": C - rng * 1.1 / 12.0,
            "Pivot": (H + L + C) / 3.0,
            "R1": C + rng * 1.1 / 12.0,
            "R2": C + rng * 1.1 / 6.0,
            "R3": C + rng * 1.1 / 4.0,
        }

        # ----------------------
        # Woodie's
        # ----------------------
        P_woodie = (H + L + 2.0 * open_curr) / 4.0
        pivots["Woodie's"] = {
            "S2": P_woodie - rng,
            "S1": 2.0 * P_woodie - H,
            "Pivot": P_woodie,
            "R1": 2.0 * P_woodie - L,
            "R2": P_woodie + rng,
        }

        # ----------------------
        # DeMark's
        # ----------------------
        # Legacy uses prev close vs current open for branch decision.
        if C < open_curr:
            X = H + 2.0 * L + C
        elif C > open_curr:
            X = 2.0 * H + L + C
        else:
            X = H + L + 2.0 * C

        P_demark = X / 4.0
        pivots["DeMark's"] = {
            "S1": X / 2.0 - H,
            "Pivot": P_demark,
            "R1": X / 2.0 - L,
        }

        # Pylance-safe timestamps (avoid pd.Timestamp(Index[...]) diagnostics)
        last_ts = cast(pd.Timestamp, idx[-1])
        prev_ts = cast(pd.Timestamp, idx[-2])

        asof_date = pd.Timestamp(last_ts).normalize()
        based_on_date = pd.Timestamp(prev_ts).normalize()

        log.info(
            "Calculated pivots for %s based on %s OHLC.",
            asof_date.strftime("%Y-%m-%d"),
            based_on_date.strftime("%Y-%m-%d"),
        )
        return PivotCalcResult(
            pivot_data=pivots,
            asof_date=asof_date,
            based_on_date=based_on_date,
        )

    except Exception as e:
        log.error("Error calculating latest pivot points: %s", e, exc_info=True)
        return None


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------


def format_pivot_table(
    pivot_data: Optional[Mapping[str, Mapping[str, Any]]],
    ticker: str,
    date: pd.Timestamp,
    *,
    decimals: int = 3,
) -> str:
    """
    Format a pivot dict into a markdown table (legacy-compatible style).

    Parameters
    ----------
    pivot_data:
        Dict like { "Classic": {"S1":..., "Pivot":..., "R1":...}, ... }
    ticker:
        Symbol label for header.
    date:
        As-of date for header (typically the current bar date).
    decimals:
        Decimal places for numeric formatting.

    Returns
    -------
    str
        Markdown block.
    """
    dt = pd.Timestamp(date)
    date_str = dt.strftime("%Y-%m-%d")

    if not pivot_data:
        return f"Could not calculate pivot points for {ticker} for {date_str}."

    header = f"#### Pivot Points for {ticker} ({date_str}):"
    headers = (
        "| Method      | S3    | S2    | S1    | Pivot Points | R1    | R2    | R3    |"
    )
    separator = (
        "|-------------|-------|-------|-------|--------------|-------|-------|-------|"
    )

    methods = ["Classic", "Fibonacci", "Camarilla", "Woodie's", "DeMark's"]
    levels = ["S3", "S2", "S1", "Pivot", "R1", "R2", "R3"]

    lines = [header, headers, separator]

    for method in methods:
        if method not in pivot_data:
            continue

        row_parts = [f"| {method:<11}"]
        m = pivot_data[method]

        for level in levels:
            v = m.get(level, None) if isinstance(m, Mapping) else None
            if v is None or (
                isinstance(v, float) and (np.isnan(v) or not np.isfinite(v))
            ):
                val_str = "-"
            else:
                try:
                    val_str = f"{float(v):.{int(decimals)}f}"
                except Exception:
                    val_str = "-"
            row_parts.append(f"| {val_str:>6} ")

        row_parts.append("|")
        lines.append("".join(row_parts))

    return "\n".join(lines)


__all__ = [
    "PivotCalcResult",
    "calculate_latest_pivot_points",
    "format_pivot_table",
]
