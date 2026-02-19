# ------------------------
# scripts/make_fh3_table.py
# ------------------------
"""
FIN FH3 Table Utility

Purpose
-------
Create a paste-ready FH=3 forecast table across the canonical ticker set.

Key behaviors (refactor-aligned)
-------------------------------
- Uses FIN path layer: src.config.paths
- Uses FIN canonical loader: src.data.loading.fetch_data
- Uses FIN model facade location: compat/Models.py (legacy-imported as "Models")
- Does NOT require technical indicators; operates on Close-only data.
- Produces:
    1) Full table with model provenance (Model_Used / Col_Used)
    2) Minimal paste-ready table for prompt injection

Assumptions
-----------
- Run from FIN project root (recommended):
    python scripts/make_fh3_table.py
- Repo root contains:
    compat/Models.py
    src/config/paths.py
    src/data/loading.py
- Raw CSV naming convention:
  data/raw/{TICKER}_data.csv
  with SPX mapped to GSPC (file) but printed as SPX (logical).
"""

from __future__ import annotations

import logging
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

import pandas as pd

from src.config import paths
from src.data.loading import fetch_data

# ---------------------------------------------------------------------
# BOOTSTRAP: compat/ on sys.path for legacy Models.py + optional Constants.py
# ---------------------------------------------------------------------
APP_ROOT = paths.APP_ROOT
COMPAT_DIR = (APP_ROOT / "compat").resolve()
if COMPAT_DIR.exists() and str(COMPAT_DIR) not in sys.path:
    sys.path.insert(0, str(COMPAT_DIR))

Models = importlib.import_module("Models")

# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("make_fh3_table")

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

TICKERS: Sequence[str] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")
FILE_PREFIX_MAP: Dict[str, str] = {"SPX": "GSPC"}
RAW_SUFFIX = "_data.csv"

MODEL_PRIORITY: List[Tuple[str, str]] = [
    ("DYNAMIX", "DYNAMIX_Pred"),
    ("ARIMAX", "ARIMAX_Pred"),
    ("ETS", "ETS_Pred"),
    ("RW", "RW_Pred"),
]

DEFAULT_FH = 3


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------
def file_prefix(ticker: str) -> str:
    return FILE_PREFIX_MAP.get(ticker, ticker)


def yyyymmdd(x: Any) -> str:
    return pd.Timestamp(x).strftime("%Y-%m-%d")


def _resolve_raw_path_for_logical_ticker(ticker: str) -> Path:
    prefix = file_prefix(ticker)
    return (paths.DATA_RAW_DIR / f"{prefix}{RAW_SUFFIX}").resolve()


def load_ticker_df_close_only(ticker: str) -> pd.DataFrame:
    """
    Load raw OHLCV via canonical loader, then:
    - Validate Close exists
    - Coerce Close numeric and drop NaN
    - Force business-day frequency with forward fill
    """
    csv_path = _resolve_raw_path_for_logical_ticker(ticker)
    df = fetch_data(ticker, csv_path=csv_path)
    if df is None or df.empty:
        raise FileNotFoundError(f"{ticker}: could not load data from {csv_path}")

    if "Close" not in df.columns:
        raise ValueError(f"{ticker}: missing Close column. Found: {list(df.columns)}")

    df = df.copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = cast(pd.DataFrame, df.dropna(subset=["Close"]))
    if df.empty:
        raise ValueError(f"{ticker}: empty after Close coercion/dropna.")

    # Ensure business-day regularity (models expect it)
    df = cast(pd.DataFrame, df.asfreq("B").ffill())
    if df.empty:
        raise ValueError(f"{ticker}: empty after asfreq('B')/ffill().")

    return df


def safe_run_arimax(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    try:
        arimax_df, _, _ = Models.predict_arima(df, ticker=ticker, exo_config=None)
        if arimax_df is not None and not arimax_df.empty:
            return cast(pd.DataFrame, arimax_df)
        return None
    except Exception as e:
        log.warning("ARIMAX failed for %s: %s", ticker, e, exc_info=True)
        return None


def safe_run_dynamix(df: pd.DataFrame, ticker: str, fh: int) -> Optional[pd.DataFrame]:
    try:
        pred_df = Models.predict_dynamix(
            df,
            ticker=ticker,
            target_col="Close",
            fh=int(fh),
        )
        if pred_df is not None and not pred_df.empty:
            return cast(pd.DataFrame, pred_df)
        return None
    except Exception as e:
        log.warning("DynaMix failed for %s: %s", ticker, e, exc_info=True)
        return None


def safe_run_ets(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    try:
        ets_df = Models.predict_exp_smoothing(df)
        if ets_df is not None and not ets_df.empty:
            return cast(pd.DataFrame, ets_df)
        return None
    except Exception as e:
        log.warning("ETS failed for %s: %s", ticker, e, exc_info=True)
        return None


def safe_run_rw(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    try:
        rw_df = Models.predict_random_walk(df)
        if rw_df is not None and not rw_df.empty:
            return cast(pd.DataFrame, rw_df)
        return None
    except Exception as e:
        log.warning("RW failed for %s: %s", ticker, e, exc_info=True)
        return None


def compute_forecasts(df: pd.DataFrame, ticker: str) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}

    fh = discover_fh()

    dynamix_df = safe_run_dynamix(df, ticker, fh)
    if dynamix_df is not None:
        out["DYNAMIX"] = dynamix_df

    arimax_df = safe_run_arimax(df, ticker)
    if arimax_df is not None:
        out["ARIMAX"] = arimax_df

    ets_df = safe_run_ets(df, ticker)
    if ets_df is not None:
        out["ETS"] = ets_df

    rw_df = safe_run_rw(df, ticker)
    if rw_df is not None:
        out["RW"] = rw_df

    return out


def select_final_path(forecasts: Dict[str, pd.DataFrame]) -> Tuple[str, str, pd.Series]:
    """
    Choose the first available forecast series per MODEL_PRIORITY.
    Returns: (model_name, column_name, series)
    """
    for model_name, col in MODEL_PRIORITY:
        if model_name in forecasts and col in forecasts[model_name].columns:
            ser_any = forecasts[model_name].loc[:, col]
            ser = cast(pd.Series, ser_any)
            return model_name, col, ser.copy()

    raise RuntimeError(
        "No usable forecast series found. Checked: "
        + ", ".join([f"{m}:{c}" for m, c in MODEL_PRIORITY])
    )


def enforce_fh(s: pd.Series, fh: int, ticker: str) -> pd.Series:
    out = s.iloc[:fh]
    if len(out) != fh:
        raise RuntimeError(f"{ticker}: expected FH={fh}, got {len(out)}")
    return out


def discover_fh() -> int:
    """
    Prefer Constants.FH if compat/Constants.py exists; otherwise default to 3.
    """
    try:
        if str(COMPAT_DIR) not in sys.path:
            sys.path.insert(0, str(COMPAT_DIR))
        import Constants as C  # type: ignore

        fh = int(getattr(C, "FH", DEFAULT_FH))
        return fh if fh > 0 else DEFAULT_FH
    except Exception:
        return DEFAULT_FH


def _as_dt_index(idx_like: Any, *, ticker: str) -> pd.DatetimeIndex:
    """
    Convert an index-like object into DatetimeIndex and validate.
    """
    dt_idx = pd.to_datetime(idx_like, errors="coerce")
    # pd.to_datetime can return Index/DatetimeIndex depending on input
    dt_idx = cast(pd.DatetimeIndex, pd.DatetimeIndex(dt_idx))
    if dt_idx.isna().any():
        raise RuntimeError(f"{ticker}: forecast index contains non-datetime values.")
    return dt_idx


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main() -> int:
    fh = discover_fh()
    if fh != 3:
        log.warning(
            "Detected FH=%s. This script is designed for FH=3, but will use FH anyway.",
            fh,
        )

    rows: List[Dict[str, Any]] = []

    for ticker in TICKERS:
        log.info("Processing %s ...", ticker)
        df = load_ticker_df_close_only(ticker)
        last_close = float(df["Close"].iloc[-1])

        forecasts = compute_forecasts(df, ticker)
        model_used, col_used, s = select_final_path(forecasts)
        s = enforce_fh(s, fh, ticker)

        # Fix for Pylance: idx[0] was inferred as Timestamp, then used as subscriptable.
        # Enforce DatetimeIndex explicitly.
        dt_idx = _as_dt_index(s.index, ticker=ticker)

        # Ensure at least fh elements exist (enforce_fh already did it; this keeps types consistent)
        if len(dt_idx) < fh:
            raise RuntimeError(
                f"{ticker}: expected FH={fh} datetime index values, got {len(dt_idx)}"
            )

        rows.append(
            {
                "Ticker": ticker,
                "FilePrefix": file_prefix(ticker),
                "Last_Close_ASOF": last_close,
                "Model_Used": model_used,
                "Col_Used": col_used,
                "FH_Date1": yyyymmdd(dt_idx[0]),
                "FH_Day1": float(s.iloc[0]),
                "FH_Date2": yyyymmdd(dt_idx[1]),
                "FH_Day2": float(s.iloc[1]),
                "FH_Date3": yyyymmdd(dt_idx[2]),
                "FH_Day3": float(s.iloc[2]),
            }
        )

    out_df = pd.DataFrame(rows)

    print(out_df.to_string(index=False))

    minimal_cols = [
        "Ticker",
        "Last_Close_ASOF",
        "FH_Date1",
        "FH_Day1",
        "FH_Date2",
        "FH_Day2",
        "FH_Date3",
        "FH_Day3",
    ]
    print("\nPASTE-READY (minimal) FORECAST_TABLE_ALL_TICKERS:")
    print(out_df[minimal_cols].to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
