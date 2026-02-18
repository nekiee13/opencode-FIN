# ------------------------
# src/structural/svl_indicators.py
# ------------------------
# FILE: F:\xPy\FIN\src\structural\svl_indicators.py
"""FIN SVL-v1.0 (Fractal-only, Daily) Structural Indicators.

Location
--------
  src/structural/svl_indicators.py

Purpose
-------
Compute STRUCTURAL_CONTEXT for tickers using daily OHLCV:
  - Hurst (H20/H60/H120) + Regime_current
  - H20_last10 mini-history (last 10 business days) + RegimeChange_last10
  - Trend10D: UP|DOWN|FLAT from Close over last 10 business days (±1% thresholds)
  - Williams Fractals (5-bar) signal over last 5 confirmed bars + level

Design constraints (Refactor Phase 1)
------------------------------------
- Side-effect free on import (no filesystem mutation).
- Optional yfinance import is isolated inside load_ohlcv_from_yfinance().

Notes
-----
- Williams fractals confirmed only up to t-2 (need two future bars).
- Hurst uses simple R/S estimator on log(Close): H = log(R/S) / log(n)
- Regime thresholds:
    PERSISTENT > 0.55, RANDOM [0.45..0.55], MEAN_REVERT < 0.45
- Trend10D:
    UP if >= +1%, DOWN if <= -1%, else FLAT
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd


# ----------------------------
# SVL-v1.0 constants
# ----------------------------

HURST_THRESH_PERSISTENT = 0.55
HURST_THRESH_MEANREVERT = 0.45

TREND10D_UP_THRESH = 0.01  # +1.0%
TREND10D_DOWN_THRESH = -0.01  # -1.0%

H20_HISTORY_LEN = 10

WILLIAMS_CONFIRM_LAG = 2  # fractals confirmed up to t-2
WILLIAMS_LOOKBACK_CONFIRMED = 5  # scan last 5 confirmed bars (t-6..t-2)


# ----------------------------
# Data structures
# ----------------------------


@dataclass(frozen=True)
class WilliamsSignal:
    signal_last5: str  # BULLISH | BEARISH | NONE
    level: Optional[float]
    note: str = ""


@dataclass(frozen=True)
class HurstPack:
    h20_current: Optional[float]
    h60_current: Optional[float]
    h120_current: Optional[float]
    regime_current: str  # PERSISTENT | RANDOM | MEAN_REVERT | UNKNOWN
    h20_last10: List[Optional[float]]  # oldest -> newest
    regime_change_last10: str  # YES | NO | UNKNOWN
    regime_change_note: str


@dataclass(frozen=True)
class TickerStructuralContext:
    ticker: str
    asof_date: str  # YYYY-MM-DD (last available close for this ticker)
    hurst: HurstPack
    trend10d: str  # UP | DOWN | FLAT
    williams: WilliamsSignal
    provenance: Dict[str, str]


# ----------------------------
# Utility helpers
# ----------------------------


def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None or pd.isna(x):
            return None
        v = float(x)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def hurst_regime(h: Optional[float]) -> str:
    if h is None:
        return "UNKNOWN"
    if h > HURST_THRESH_PERSISTENT:
        return "PERSISTENT"
    if h < HURST_THRESH_MEANREVERT:
        return "MEAN_REVERT"
    return "RANDOM"


def regime_current(
    h20: Optional[float], h60: Optional[float], h120: Optional[float]
) -> Tuple[str, str]:
    """Compute Regime_current from median(H20,H60) with H120 advisory note."""
    note_parts: List[str] = []
    vals = [v for v in (h20, h60) if v is not None]

    base: Optional[float]
    if len(vals) == 2:
        base = float(np.median(vals))
    elif len(vals) == 1:
        base = float(vals[0])
        note_parts.append(
            "Regime_current based on single available H window (H20 or H60)."
        )
    else:
        base = None
        note_parts.append("Hurst unavailable; regime set to UNKNOWN.")

    reg = hurst_regime(base)

    if h120 is not None and base is not None:
        reg120 = hurst_regime(h120)
        if reg120 not in ("UNKNOWN", reg):
            note_parts.append(
                f"H120 suggests broader regime differs ({reg120}); interpret near-term regime with caution."
            )

    return reg, " ".join(note_parts).strip()


# ----------------------------
# Hurst computation (R/S estimator on log prices)
# ----------------------------


def compute_hurst_rs(
    log_prices: np.ndarray, window: Optional[int] = None
) -> Optional[float]:
    """
    Simple R/S Hurst estimator on a single window of log prices.

    If ``window`` is provided, require at least ``window + 1`` observations
    (window returns) to compute a stable estimate.
    """
    x = np.asarray(log_prices, dtype=float)
    if window is not None and x.size < int(window) + 1:
        return None
    if x.size < 6 or np.any(~np.isfinite(x)):
        return None

    inc = np.diff(x)
    n = inc.size
    if n < 5:
        return None

    inc_centered = inc - float(np.mean(inc))
    cum = np.cumsum(inc_centered)

    R = float(np.max(cum) - np.min(cum))
    S = float(np.std(inc, ddof=1))

    if not np.isfinite(R) or not np.isfinite(S) or R <= 0.0 or S <= 0.0:
        return None

    H = float(np.log(R / S) / np.log(float(n)))
    if not np.isfinite(H):
        return None

    return float(clamp(H, 0.0, 1.0))


def compute_hurst_for_window(close: pd.Series, window: int) -> Optional[float]:
    """
    Pylance note
    ------------
    Some call sites can be widened to Unknown/Any when values originate from DataFrame indexing.
    A local cast is applied to enforce the expected Series type for static analysis.
    """
    s = cast(pd.Series, close)
    if s is None or len(s) < int(window):
        return None
    win = cast(pd.Series, s.iloc[-int(window) :]).astype(float)
    if win.isna().any():
        return None
    logp = np.log(win.to_numpy(dtype=float))
    return compute_hurst_rs(logp)


def compute_hurst_rolling_endpoints(
    close: pd.Series, window: int, last_k: int
) -> List[Optional[float]]:
    """Compute Hurst(window) ending at each of the last `last_k` endpoints."""
    s = cast(pd.Series, close)
    if s is None or s.empty:
        return [None] * int(last_k)

    close_f = s.astype(float)

    results: List[Optional[float]] = []
    k = int(last_k)
    for i in range(k):
        end_idx = len(close_f) - k + i + 1
        if end_idx <= 0:
            results.append(None)
            continue
        segment = cast(pd.Series, close_f.iloc[:end_idx])
        results.append(compute_hurst_for_window(segment, int(window)))

    if len(results) < k:
        results = ([None] * (k - len(results))) + results
    return results[-k:]


# ----------------------------
# Trend10D
# ----------------------------


def compute_trend10d(close: pd.Series) -> Tuple[str, str]:
    """Trend10D from last 10 closes."""
    s = cast(pd.Series, close)
    if s is None or len(s) < 10:
        return (
            "FLAT",
            "Insufficient history for Trend10D (requires 10 closes); defaulted to FLAT.",
        )

    last10 = cast(pd.Series, s.iloc[-10:]).astype(float)
    if last10.isna().any():
        return "FLAT", "NaNs in last 10 closes for Trend10D; defaulted to FLAT."

    c0 = float(last10.iloc[0])
    c1 = float(last10.iloc[-1])
    if not np.isfinite(c0) or not np.isfinite(c1) or c0 == 0.0:
        return "FLAT", "Invalid Close values for Trend10D; defaulted to FLAT."

    delta = (c1 - c0) / c0
    if delta >= TREND10D_UP_THRESH:
        return "UP", ""
    if delta <= TREND10D_DOWN_THRESH:
        return "DOWN", ""
    return "FLAT", ""


# ----------------------------
# Williams fractals (5-bar)
# ----------------------------


def compute_williams_fractals(high: pd.Series, low: pd.Series) -> pd.DataFrame:
    """Williams 5-bar fractals."""
    h = cast(pd.Series, high).astype(float).reset_index(drop=True)
    low_series = cast(pd.Series, low).astype(float).reset_index(drop=True)
    n = int(len(h))

    bull = np.zeros(n, dtype=bool)
    bear = np.zeros(n, dtype=bool)

    for i in range(2, n - 2):
        window_l = np.asarray(low_series.iloc[i - 2 : i + 3], dtype=float)
        if np.all(np.isfinite(window_l)):
            if (
                low_series.iloc[i] < low_series.iloc[i - 1]
                and low_series.iloc[i] < low_series.iloc[i - 2]
                and low_series.iloc[i] < low_series.iloc[i + 1]
                and low_series.iloc[i] < low_series.iloc[i + 2]
            ):
                bull[i] = True

        window_h = np.asarray(h.iloc[i - 2 : i + 3], dtype=float)
        if np.all(np.isfinite(window_h)):
            if (
                h.iloc[i] > h.iloc[i - 1]
                and h.iloc[i] > h.iloc[i - 2]
                and h.iloc[i] > h.iloc[i + 1]
                and h.iloc[i] > h.iloc[i + 2]
            ):
                bear[i] = True

    bull_level = np.where(bull, low_series.to_numpy(dtype=float), np.nan)
    bear_level = np.where(bear, h.to_numpy(dtype=float), np.nan)

    return pd.DataFrame(
        {
            "bull_fractal": bull,
            "bear_fractal": bear,
            "bull_level": bull_level,
            "bear_level": bear_level,
        }
    )


def active_fractal_last5(df_ohlcv: pd.DataFrame) -> WilliamsSignal:
    """Active fractal signal over last 5 confirmed bars (confirmed up to t-2)."""
    if df_ohlcv is None or len(df_ohlcv) < 10:
        return WilliamsSignal(
            "NONE", None, "Insufficient bars for Williams fractals scan."
        )

    fr = compute_williams_fractals(
        cast(pd.Series, df_ohlcv["High"]), cast(pd.Series, df_ohlcv["Low"])
    )

    t = int(len(fr) - 1)
    last_confirmed = t - WILLIAMS_CONFIRM_LAG
    start = max(0, last_confirmed - (WILLIAMS_LOOKBACK_CONFIRMED - 1))

    if last_confirmed < 0 or start > last_confirmed:
        return WilliamsSignal(
            "NONE", None, "No confirmed bars available for scan window."
        )

    scan = fr.iloc[start : last_confirmed + 1]

    bull_idx = scan.index[scan["bull_fractal"]].tolist()
    bear_idx = scan.index[scan["bear_fractal"]].tolist()

    if not bull_idx and not bear_idx:
        return WilliamsSignal(
            "NONE", None, "No fractals detected in last 5 confirmed bars."
        )

    last_bull = max(bull_idx) if bull_idx else None
    last_bear = max(bear_idx) if bear_idx else None

    if last_bull is not None and (last_bear is None or last_bull > last_bear):
        level = _to_float(fr.loc[last_bull, "bull_level"])
        return WilliamsSignal(
            "BULLISH", level, f"Confirmed fractal index={last_bull} (<= t-2)."
        )

    if last_bear is not None and (last_bull is None or last_bear > last_bull):
        level = _to_float(fr.loc[last_bear, "bear_level"])
        return WilliamsSignal(
            "BEARISH", level, f"Confirmed fractal index={last_bear} (<= t-2)."
        )

    return WilliamsSignal(
        "NONE", None, "Bullish and bearish fractal coincide; treated as NONE."
    )


# ----------------------------
# Regime change detection from H20_last10
# ----------------------------


def regime_change_last10(
    h20_last10: List[Optional[float]], dates_last10: Sequence[Optional[pd.Timestamp]]
) -> Tuple[str, str]:
    """Determine if regime changed across last 10 business days based on H20_last10."""
    if len(h20_last10) != len(dates_last10) or len(h20_last10) == 0:
        return "UNKNOWN", "Invalid inputs for regime change detection."

    regimes: List[Optional[str]] = []
    for h in h20_last10:
        if h is None:
            regimes.append(None)
        else:
            r = hurst_regime(h)
            regimes.append(None if r == "UNKNOWN" else r)

    valid_positions = [i for i, r in enumerate(regimes) if r is not None]
    if len(valid_positions) < 3:
        return (
            "UNKNOWN",
            "Too few valid H20 values in last10 to determine regime change.",
        )

    last_change_pos: Optional[int] = None
    last_from: Optional[str] = None
    last_to: Optional[str] = None

    prev_reg: Optional[str] = None
    for i in valid_positions:
        r = regimes[i]
        if r is None:
            continue
        if prev_reg is None:
            prev_reg = r
            continue
        if r != prev_reg:
            last_change_pos = i
            last_from = prev_reg
            last_to = r
        prev_reg = r

    if last_change_pos is None:
        return "NO", ""

    d = dates_last10[last_change_pos]
    if d is None or pd.isna(d):
        date_str = "UNKNOWN_DATE"
    else:
        date_str = cast(pd.Timestamp, d).strftime("%Y-%m-%d")
    return "YES", f"{date_str}: {last_from}→{last_to}"


# ----------------------------
# OHLCV normalization and loading
# ----------------------------


def normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV to standard columns: Open, High, Low, Close, Volume."""
    if df is None or df.empty:
        raise ValueError("Empty OHLCV DataFrame.")

    cols_lower = {str(c).lower(): c for c in df.columns}

    def pick(*names: str) -> Optional[str]:
        for n in names:
            c = cols_lower.get(n.lower())
            if c is not None:
                return c
        return None

    date_col = pick("date", "datetime", "timestamp")

    out = df.copy()
    if date_col is not None:
        out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
        out = out.dropna(subset=[date_col]).set_index(date_col)
    else:
        if not isinstance(out.index, pd.DatetimeIndex):
            raise ValueError("No Date column found and index is not a DatetimeIndex.")
        out.index = pd.to_datetime(out.index, errors="coerce")

    out = out[~out.index.isna()].sort_index()
    out = out[~out.index.duplicated(keep="last")]

    open_c = pick("open")
    high_c = pick("high")
    low_c = pick("low")
    close_c = pick("close", "adj close", "adj_close", "adjclose")
    vol_c = pick("volume", "vol")

    missing = [
        name
        for name, c in (("High", high_c), ("Low", low_c), ("Close", close_c))
        if c is None
    ]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. Found columns: {list(df.columns)}"
        )

    std = pd.DataFrame(index=out.index)
    if open_c is not None:
        std["Open"] = pd.to_numeric(out[open_c], errors="coerce")
    std["High"] = pd.to_numeric(out[high_c], errors="coerce")
    std["Low"] = pd.to_numeric(out[low_c], errors="coerce")
    std["Close"] = pd.to_numeric(out[close_c], errors="coerce")
    if vol_c is not None:
        std["Volume"] = pd.to_numeric(out[vol_c], errors="coerce")

    std = std.dropna(subset=["High", "Low", "Close"]).sort_index()
    return std


def load_ohlcv_from_csv(csv_path: Path) -> pd.DataFrame:
    """Load raw CSV into a DataFrame (normalization occurs later)."""
    return pd.read_csv(csv_path)


def load_ohlcv_from_yfinance(yf_ticker: str, period: str = "2y") -> pd.DataFrame:
    """Optional loader: returns a DataFrame with a date column suitable for normalize_ohlcv_columns()."""
    try:
        import yfinance as yf  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "yfinance not installed. Install via: pip install yfinance"
        ) from e

    data = yf.download(
        yf_ticker, period=period, interval="1d", auto_adjust=False, progress=False
    )
    if data is None or data.empty:
        raise RuntimeError(f"No data returned from yfinance for {yf_ticker}")
    return data.reset_index()


# ----------------------------
# Core computation per ticker
# ----------------------------


def compute_structural_context_for_ticker(
    ticker: str,
    df_ohlcv_raw: pd.DataFrame,
    data_source: str,
    computed_on: str,
    method_notes: str,
) -> TickerStructuralContext:
    def _fallback_context(note: str) -> TickerStructuralContext:
        fallback_asof = (
            str(computed_on).split(" ", 1)[0]
            if str(computed_on).strip()
            else "1970-01-01"
        )
        prov = {
            "computed_on": computed_on,
            "data_source": data_source,
            "sampling": "1D",
            "method_notes": " | ".join([p for p in (method_notes, note) if p]).strip(),
        }
        return TickerStructuralContext(
            ticker=ticker,
            asof_date=fallback_asof,
            hurst=HurstPack(
                h20_current=None,
                h60_current=None,
                h120_current=None,
                regime_current="UNKNOWN",
                h20_last10=[None] * H20_HISTORY_LEN,
                regime_change_last10="UNKNOWN",
                regime_change_note="Insufficient data for regime-change detection.",
            ),
            trend10d="FLAT",
            williams=WilliamsSignal(
                "NONE", None, "Insufficient bars for Williams fractals scan."
            ),
            provenance=prov,
        )

    try:
        df = normalize_ohlcv_columns(df_ohlcv_raw)
    except Exception as e:
        return _fallback_context(f"Normalization failed: {type(e).__name__}: {e}")

    if df.empty:
        return _fallback_context("OHLCV data is empty after normalization.")

    # Avoid pd.Timestamp(Index[Any]) patterns; df.index[-1] is scalar-like.
    asof_date = cast(pd.Timestamp, pd.Timestamp(cast(Any, df.index[-1]))).strftime(
        "%Y-%m-%d"
    )

    close = cast(pd.Series, df["Close"]).copy()

    h20 = compute_hurst_for_window(close, 20)
    h60 = compute_hurst_for_window(close, 60)
    h120 = compute_hurst_for_window(close, 120)

    reg_cur, reg_note = regime_current(h20, h60, h120)

    h20_last10 = compute_hurst_rolling_endpoints(close, 20, H20_HISTORY_LEN)

    dates_last10: List[Optional[pd.Timestamp]]
    if len(df) >= H20_HISTORY_LEN:
        dates_last10 = [
            cast(pd.Timestamp, pd.Timestamp(cast(Any, d)))
            for d in df.index[-H20_HISTORY_LEN:]
        ]
    else:
        dates_last10 = [
            cast(pd.Timestamp, pd.Timestamp(cast(Any, d))) for d in df.index
        ]
        while len(dates_last10) < H20_HISTORY_LEN:
            dates_last10.insert(0, None)

    rc_flag, rc_note = regime_change_last10(h20_last10, dates_last10)

    trend10d, trend_note = compute_trend10d(close)

    will = active_fractal_last5(df)

    note_parts: List[str] = [method_notes]
    if reg_note:
        note_parts.append(reg_note)
    if trend_note:
        note_parts.append(trend_note)
    if will.note:
        note_parts.append(f"Williams: {will.note}")

    hurst_pack = HurstPack(
        h20_current=_to_float(h20),
        h60_current=_to_float(h60),
        h120_current=_to_float(h120),
        regime_current=reg_cur,
        h20_last10=[_to_float(x) for x in h20_last10],
        regime_change_last10=rc_flag,
        regime_change_note=rc_note,
    )

    prov = {
        "computed_on": computed_on,
        "data_source": data_source,
        "sampling": "1D",
        "method_notes": " | ".join([p for p in note_parts if p]).strip(),
    }

    return TickerStructuralContext(
        ticker=ticker,
        asof_date=asof_date,
        hurst=hurst_pack,
        trend10d=trend10d,
        williams=WilliamsSignal(will.signal_last5, will.level, will.note),
        provenance=prov,
    )


# ----------------------------
# Export
# ----------------------------


def _fmt_float(x: Optional[float], nd: int = 2) -> str:
    return "NA" if x is None else f"{x:.{nd}f}"


def export_structural_context_markdown(
    contexts: List[TickerStructuralContext], global_asof_date: str
) -> str:
    lines: List[str] = []
    lines.append("STRUCTURAL_CONTEXT (Computed from internal OHLCV; no web citations)")
    lines.append("")
    lines.append(f"As-of (last close): {global_asof_date}")
    sources = sorted({c.provenance.get("data_source", "UNKNOWN") for c in contexts})
    lines.append(
        f"Data source: {sources[0] if len(sources) == 1 else 'Mixed (per ticker); see Provenance'}"
    )
    lines.append(
        "Lookbacks: H20/H60/H120; Williams fractals (5-bar); H20 mini-history = last 10 business days"
    )
    lines.append(
        "Trend definition: Trend10D computed from Close over last 10 business days (UP if >= +1%, DOWN if <= -1%, else FLAT)"
    )
    lines.append("")

    for c in contexts:
        method_notes_s = (c.provenance.get("method_notes", "") or "").replace('"', "'")
        will_note_s = (c.williams.note or "").replace('"', "'")
        h20_list_str = ", ".join(_fmt_float(v, 2) for v in c.hurst.h20_last10)
        lvl_str = "NA" if c.williams.level is None else f"{c.williams.level:.2f}"

        lines.append(f"[{c.ticker}]")
        lines.append("Hurst:")
        lines.append(f"  H20_current: {_fmt_float(c.hurst.h20_current, 2)}")
        lines.append(f"  H60_current: {_fmt_float(c.hurst.h60_current, 2)}")
        lines.append(f"  H120_current: {_fmt_float(c.hurst.h120_current, 2)}")
        lines.append(f"  Regime_current: {c.hurst.regime_current}")
        lines.append(f"  H20_last10: [{h20_list_str}]")
        lines.append(f"  RegimeChange_last10: {c.hurst.regime_change_last10}")
        lines.append(f'  RegimeChange_note: "{c.hurst.regime_change_note}"')
        lines.append(f"Trend10D: {c.trend10d}")
        lines.append("WilliamsFractals:")
        lines.append(f"  Signal_last5: {c.williams.signal_last5}")
        lines.append(f"  Level: {lvl_str}")
        lines.append(f'  Note: "{will_note_s}"')
        lines.append("Provenance:")
        lines.append(f"  computed_on: {c.provenance.get('computed_on', '')}")
        lines.append(f'  method_notes: "{method_notes_s}"')
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def export_metrics_csv(contexts: List[TickerStructuralContext]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for c in contexts:
        rows.append(
            {
                "Ticker": c.ticker,
                "Ticker_AsOf": c.asof_date,
                "H20": c.hurst.h20_current,
                "H60": c.hurst.h60_current,
                "H120": c.hurst.h120_current,
                "Regime_current": c.hurst.regime_current,
                "RegimeChange_last10": c.hurst.regime_change_last10,
                "RegimeChange_note": c.hurst.regime_change_note,
                "Trend10D": c.trend10d,
                "Williams_Signal_last5": c.williams.signal_last5,
                "Williams_Level": c.williams.level,
                "Computed_on": c.provenance.get("computed_on", ""),
                "Data_source": c.provenance.get("data_source", ""),
            }
        )
    return pd.DataFrame(rows)


# ----------------------------
# CLI (optional direct runner)
# ----------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="SVL-v1.0 StructuralIndicators generator (Fractal-only, Daily)."
    )
    p.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="Logical tickers (e.g., TNX DJI SPX VIX QQQ AAPL).",
    )

    p.add_argument(
        "--csv-dir",
        type=str,
        default=None,
        help="Directory containing per-ticker CSV files.",
    )
    p.add_argument(
        "--csv-suffix",
        type=str,
        default=".csv",
        help="CSV filename suffix (default: .csv).",
    )

    p.add_argument(
        "--yfinance", action="store_true", help="Fetch data via yfinance (optional)."
    )
    p.add_argument(
        "--yf-period", type=str, default="2y", help="yfinance period (default: 2y)."
    )

    p.add_argument(
        "--map-json",
        type=str,
        default=None,
        help="Optional JSON string or JSON file path mapping logical tickers to data tickers.",
    )

    p.add_argument(
        "--out-md",
        type=str,
        default=None,
        help="Write STRUCTURAL_CONTEXT markdown to this file.",
    )
    p.add_argument(
        "--out-csv",
        type=str,
        default=None,
        help="Write summary SVL metrics to this CSV file.",
    )
    p.add_argument(
        "--print",
        action="store_true",
        help="Print markdown to stdout (default if no --out-md).",
    )
    p.add_argument(
        "--method-notes",
        type=str,
        default="",
        help="Additional method notes to include in provenance.",
    )
    return p.parse_args()


def load_mapping(map_json: Optional[str]) -> Dict[str, str]:
    if not map_json:
        return {}
    s = map_json.strip()
    path = Path(s)
    if path.exists() and path.is_file():
        return cast(Dict[str, str], json.loads(path.read_text(encoding="utf-8")))
    return cast(Dict[str, str], json.loads(s))


def main() -> None:
    args = parse_args()
    mapping = load_mapping(args.map_json)

    if not args.csv_dir and not args.yfinance:
        raise SystemExit("Error: provide either --csv-dir or --yfinance.")

    computed_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    base_method_notes = (
        "SVL-v1.0: Hurst via R/S on log(Close) windows; "
        "Trend10D thresholds ±1%; Williams 5-bar fractals confirmed up to t-2."
    )
    method_notes = base_method_notes
    if args.method_notes.strip():
        method_notes = f"{base_method_notes} {args.method_notes.strip()}"

    contexts: List[TickerStructuralContext] = []

    for logical in args.tickers:
        data_ticker = mapping.get(logical) or logical

        if args.csv_dir:
            csv_dir = Path(args.csv_dir)
            primary = csv_dir / f"{data_ticker}{args.csv_suffix}"
            fallback = csv_dir / f"{logical}{args.csv_suffix}"
            csv_path = primary if primary.exists() else fallback
            if not csv_path.exists():
                raise SystemExit(
                    f"Error: CSV not found for {logical}. Tried: {primary} and {fallback}"
                )

            df_raw = load_ohlcv_from_csv(csv_path)
            data_source = f"CSV:{csv_path}"
        else:
            df_raw = load_ohlcv_from_yfinance(str(data_ticker), period=args.yf_period)
            data_source = f"yfinance:{data_ticker}"

        ctx = compute_structural_context_for_ticker(
            ticker=logical,
            df_ohlcv_raw=df_raw,
            data_source=data_source,
            computed_on=computed_on,
            method_notes=method_notes,
        )
        contexts.append(ctx)

    asof_dates = [pd.to_datetime(c.asof_date) for c in contexts if c.asof_date]
    global_asof = (
        min(asof_dates).strftime("%Y-%m-%d")
        if asof_dates
        else datetime.now().strftime("%Y-%m-%d")
    )

    md = export_structural_context_markdown(contexts, global_asof)

    if args.out_md:
        out_path = Path(args.out_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")

    if args.out_csv:
        out_path = Path(args.out_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        export_metrics_csv(contexts).to_csv(out_path, index=False)

    if args.print or (not args.out_md):
        print(md)


if __name__ == "__main__":
    main()
