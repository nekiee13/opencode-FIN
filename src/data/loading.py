# ------------------------
# src/data/loading.py
# ------------------------
"""
FIN canonical data loading utilities.

Location: src/data/loading.py

Purpose
-------
Centralize CSV loading/sanitization for OHLCV-type data.

Behavioral baseline
-------------------
This module is based on the TS legacy `Data_Loading.fetch_data()` behavior:
- Locate CSV per ticker
- Detect date column from common variants
- Parse dates (prefer '%b %d, %Y', fallback to default parsing)
- Drop invalid dates, set datetime index, deduplicate, sort
- Normalize column names to Open/High/Low/Close/Volume (case-insensitive)
- Coerce numeric columns, drop rows missing essential OHLC
- Return DataFrame indexed by datetime (business-day frequency is NOT enforced here)

Path resolution
---------------
- Uses src.config.paths.DATA_TICKERS_DIR (FIN layout: data/raw/tickers/{TICKER}_data.csv)
- Transitional fallback: data/raw/{TICKER}_data.csv
- No filesystem mutation on import.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union, cast

import numpy as np
import pandas as pd

from src.config import paths

log = logging.getLogger(__name__)

PathLike = Union[str, Path]

_DATE_COL_CANDIDATES: Sequence[str] = ("Date", "date", "Datetime", "DateTime")


def _sanitize_ticker_for_filename(ticker: str) -> str:
    # TS behavior: remove '^' (e.g., '^GSPC' -> 'GSPC')
    return str(ticker).replace("^", "").strip()


def resolve_raw_csv_path(
    ticker: str,
    raw_dir: Optional[PathLike] = None,
    suffix: str = "_data.csv",
) -> Path:
    """Resolve the expected raw CSV path for a ticker."""
    sanitized = _sanitize_ticker_for_filename(ticker)
    filename = f"{sanitized}{suffix}"

    if raw_dir is not None:
        return (Path(raw_dir) / filename).resolve()

    preferred = (paths.DATA_TICKERS_DIR / filename).resolve()
    if preferred.exists():
        return preferred

    legacy = (paths.DATA_RAW_DIR / filename).resolve()
    if legacy.exists():
        return legacy

    return preferred


def detect_date_column(df: pd.DataFrame, candidates: Sequence[str] = _DATE_COL_CANDIDATES) -> Optional[str]:
    """Detect a date column name from common variants (TS behavior)."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to canonical Open/High/Low/Close/Volume if case variants exist."""
    rename_map: Dict[Any, str] = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if col_lower == "close" and col != "Close":
            rename_map[col] = "Close"
        elif col_lower == "high" and col != "High":
            rename_map[col] = "High"
        elif col_lower == "low" and col != "Low":
            rename_map[col] = "Low"
        elif col_lower == "open" and col != "Open":
            rename_map[col] = "Open"
        elif col_lower == "volume" and col != "Volume":
            rename_map[col] = "Volume"

    if rename_map:
        df = df.rename(columns=rename_map)
        log.info("Applied column renames: %s", rename_map)

    return df


def _parse_datetime_column(series: pd.Series) -> pd.Series:
    """
    Parse datetime using TS preference (format first, fallback to default).

    Notes on typing
    ---------------
    pandas.to_datetime has overloads that may return Timestamp / Series / DatetimeIndex
    depending on input shape. This helper forces a Series return to keep callers typed.
    """
    s = cast(pd.Series, series)

    try:
        out_any = pd.to_datetime(s, format="%b %d, %Y", errors="coerce")
        out = cast(pd.Series, out_any)

        # If everything became NaT, fallback
        if out.isna().all():
            raise ValueError("All dates NaT under preferred format")

        log.info("Parsed date column using format '%%b %%d, %%Y'.")
        return out

    except Exception as e:
        log.warning("Preferred date parse failed (%s). Falling back to default parsing.", e)
        out_any = pd.to_datetime(s, errors="coerce")
        return cast(pd.Series, out_any)


def fetch_data(
    ticker: str,
    *,
    csv_path: Optional[PathLike] = None,
    raw_dir: Optional[PathLike] = None,
    suffix: str = "_data.csv",
    min_rows_warn: int = 30,
) -> Optional[pd.DataFrame]:
    """
    Load and sanitize historical OHLCV data for a ticker.

    Returns
    -------
    DataFrame | None
        DataFrame indexed by DatetimeIndex, sorted ascending, duplicates removed, OHLC coerced numeric.
        Returns None on fatal issues (file missing, no date column, essential OHLC missing, etc.)
    """
    try:
        path = (
            Path(csv_path).resolve()
            if csv_path is not None
            else resolve_raw_csv_path(ticker, raw_dir=raw_dir, suffix=suffix)
        )

        if not path.exists():
            log.error("File not found: %s", path)
            return None

        log.info("Fetching data for %s from %s", ticker, path)
        df = cast(pd.DataFrame, pd.read_csv(path))

        # Date column detection
        date_col = detect_date_column(df)
        if date_col is None:
            log.error(
                "CSV for %s needs a date column (e.g., 'Date' or 'date'). Cols: %s",
                ticker,
                list(df.columns),
            )
            return None

        log.info("Found date column: '%s'", date_col)

        # Parse dates
        df[date_col] = _parse_datetime_column(cast(pd.Series, df[date_col]))

        # Drop invalid dates
        df = cast(pd.DataFrame, df.dropna(subset=[date_col]))
        if df.empty:
            log.error("No valid dates found for %s after parsing.", ticker)
            return None

        # Set index (cast avoids pandas stub unions: DataFrame | Series)
        df = cast(pd.DataFrame, df.set_index(date_col))
        df.index.name = "date"

        # Ensure DatetimeIndex (robust coercion path)
        if not isinstance(df.index, pd.DatetimeIndex):
            log.warning("Index not DatetimeIndex for %s after initial processing. Converting.", ticker)

            idx_any = pd.to_datetime(df.index, errors="coerce")
            idx = cast(pd.DatetimeIndex, pd.DatetimeIndex(idx_any))

            mask_valid = ~idx.isna()
            if mask_valid.sum() == 0:
                log.error("Failed to coerce any index values to datetime for %s.", ticker)
                return None

            df = cast(pd.DataFrame, df.loc[mask_valid].copy())
            df.index = cast(pd.DatetimeIndex, idx[mask_valid])
            df.index.name = "date"

        # Remove duplicated index entries
        if df.index.duplicated().any():
            num_dup = int(df.index.duplicated().sum())
            log.warning("Found %d duplicate indices in %s. Keeping last.", num_dup, ticker)
            df = cast(pd.DataFrame, df[~df.index.duplicated(keep="last")])

        # Sort index
        if not df.index.is_monotonic_increasing:
            log.warning("Index for %s not sorted. Sorting.", ticker)
            df = cast(pd.DataFrame, df.sort_index())

        # Volume '-' replacement (TS behavior)
        if "Volume" in df.columns and df["Volume"].dtype == "object":
            vol = cast(pd.Series, df["Volume"]).replace("-", np.nan)
            df["Volume"] = vol
            log.info("Replaced '-' with NaN in 'Volume' column.")

        # Normalize column names (cast avoids pandas stub unions)
        df = normalize_ohlcv_columns(cast(pd.DataFrame, df))

        # Coerce numeric columns (Volume may be missing)
        numeric_columns = ["Close", "High", "Low", "Open", "Volume"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            elif col != "Volume":
                log.warning("Expected numeric column '%s' not found in data for %s.", col, ticker)

        # Validate essential OHLC
        essential_cols = ["Open", "High", "Low", "Close"]
        if not all(c in df.columns for c in essential_cols):
            log.error(
                "Essential OHLC columns ('Open', 'High', 'Low', 'Close') missing or incomplete in %s.",
                ticker,
            )
            return None

        # Drop rows missing essential OHLC
        initial_rows = len(df)
        df = cast(pd.DataFrame, df.dropna(subset=essential_cols))
        dropped = initial_rows - len(df)
        if dropped > 0:
            log.warning("Dropped %d rows with NaN in essential OHLC for %s.", dropped, ticker)

        if len(df) < min_rows_warn:
            log.warning(
                "Insufficient data (%d rows) for %s for reliable analysis after cleaning.",
                len(df),
                ticker,
            )

        log.info("Loaded %d processed data points for %s.", len(df), ticker)
        return df

    except Exception as e:
        log.error("Error fetching/processing raw %s data: %s", ticker, e, exc_info=True)
        return None


__all__ = [
    "fetch_data",
    "resolve_raw_csv_path",
    "detect_date_column",
    "normalize_ohlcv_columns",
]
