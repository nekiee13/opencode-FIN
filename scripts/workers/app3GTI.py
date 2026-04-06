# ------------------------
# scripts\workers\app3GTI.py
# ------------------------
"""
FIN Technical Indicators Worker (subprocess)

Contract with main orchestrator (Models.run_external_script)
-----------------------------------------------------------
- Invoked as:  python app3GTI.py <TICKER>
- Loads raw OHLCV from FIN layout: data/raw/tickers/{TICKER}_data.csv (fallback: data/raw/{TICKER}_data.csv)
- Adds technical indicators (TA-Lib) + classic pivots
- Enforces business-day frequency (asfreq('B') with ffill/bfill on OHLC)
- Writes enriched DataFrame to a temporary CSV file
- Prints the temp CSV file path to STDOUT (single line)
- All diagnostics go to STDERR
- Exit code 0 on success, non-zero on failure

Design notes
------------
- No absolute paths.
- Robust sys.path bootstrap so it runs from scripts/workers.
- Uses FIN canonical loader to keep raw parsing logic centralized.
- Keeps indicator naming compatible with your legacy pipeline (Models.py + plotting):
    MA50, MA200, RSI (14), Stochastic %K, STOCH_%D, ATR (14), ADX (14), CCI (14),
    ROC (10), Ultimate Oscillator, Williams %R, BullBear Power, plus pivot columns.

Optional dependency
-------------------
- TA-Lib must be installed in the environment used to execute this worker.
- Help mode (--help) must succeed even if TA-Lib is missing.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import traceback
import warnings
from pathlib import Path
from typing import Optional, cast

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# ----------------------------
# Diagnostics helpers
# ----------------------------


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


# ----------------------------
# sys.path bootstrap (so src.* works when run from scripts/workers)
# ----------------------------


def _bootstrap_sys_path() -> Path:
    this_file = Path(__file__).resolve()
    workers_dir = this_file.parent
    scripts_dir = workers_dir.parent
    app_root = scripts_dir.parent  # FIN root

    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    compat_dir = app_root / "compat"
    if compat_dir.exists() and str(compat_dir) not in sys.path:
        sys.path.insert(0, str(compat_dir))

    return app_root


APP_ROOT = _bootstrap_sys_path()


# ----------------------------
# FIN imports (after bootstrap)
# ----------------------------

try:
    from src.config import paths
except Exception as e:
    raise RuntimeError(
        "Failed to import FIN path layer: from src.config import paths. "
        "Ensure src/config/paths.py exists and src/ is a package."
    ) from e

try:
    from src.data.loading import fetch_data, resolve_raw_csv_path
except Exception as e:
    raise RuntimeError(
        "Failed to import FIN loader: from src.data.loading import fetch_data. "
        "Ensure src/data/loading.py exists."
    ) from e


# ----------------------------
# Configuration
# ----------------------------

DEFAULT_TICKER = "TNX"
TARGET_COLUMN = "Close"


# ----------------------------
# CLI
# ----------------------------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Legacy contract: python app3GTI.py <TICKER>
    Also supports:  python app3GTI.py --ticker <TICKER>
    """
    p = argparse.ArgumentParser(
        prog="app3GTI.py",
        description="FIN technical indicators worker (writes temp CSV path to stdout; diagnostics on stderr).",
    )

    p.add_argument(
        "ticker",
        nargs="?",
        default=None,
        help="Ticker symbol (legacy positional). Example: TNX",
    )
    p.add_argument(
        "--ticker",
        dest="ticker_flag",
        default=None,
        help="Ticker symbol (explicit form). If provided, overrides positional ticker.",
    )
    p.add_argument(
        "--history-mode",
        choices=["live", "replay"],
        default="live",
        help="History scope mode. replay clips loader data to --as-of-date.",
    )
    p.add_argument(
        "--as-of-date",
        default=None,
        help="Required when --history-mode replay (YYYY-MM-DD).",
    )

    return p.parse_args(argv)


def _resolve_ticker(args: argparse.Namespace) -> str:
    if getattr(args, "ticker_flag", None):
        return str(args.ticker_flag)
    if getattr(args, "ticker", None):
        return str(args.ticker)
    return DEFAULT_TICKER


# ----------------------------
# Optional dependency: TA-Lib - deferred so --help works without talib
# ----------------------------


def _require_talib() -> None:
    try:
        import talib  # noqa: F401
    except Exception as e:
        eprint("TA-Lib is not available in this environment.")
        eprint("Install (example): pip install TA-Lib")
        eprint(f"Import error: {e}")
        raise


# ----------------------------
# Helper: Business-day regularization
# ----------------------------


def ensure_business_day_ohlc(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Force business-day frequency and fill OHLC gaps conservatively.

    - asfreq('B') to introduce missing business days
    - ffill/bfill OHLC columns
    - drop remaining NaNs in OHLC (fatal if empty)
    """
    if df is None or df.empty:
        return None

    required = ["Open", "High", "Low", "Close"]
    if not all(c in df.columns for c in required):
        eprint(
            f"TI worker: missing OHLC columns before asfreq: required={required}, cols={list(df.columns)}"
        )
        return None

    try:
        df_b = cast(pd.DataFrame, df.asfreq("B"))
        for c in required:
            if df_b[c].isnull().any():
                df_b[c] = df_b[c].ffill().bfill()

        before = len(df_b)
        df_b = cast(pd.DataFrame, df_b.dropna(subset=required, how="any"))
        if df_b.empty and before > 0:
            eprint(
                "TI worker: data became empty after business-day regularization and OHLC NaN drop."
            )
            return None

        # If Volume exists and is entirely NaN, drop it (legacy behavior)
        if "Volume" in df_b.columns and df_b["Volume"].isnull().all():
            eprint("TI worker: Volume column is all NaNs; dropping Volume.")
            df_b = df_b.drop(columns=["Volume"])

        return df_b

    except Exception as e:
        eprint(f"TI worker: business-day regularization failed: {e}")
        traceback.print_exc(file=sys.stderr)
        return None


# ----------------------------
# Classic pivot points
# ----------------------------


def calculate_classic_pivot_points(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds classic pivots based on previous day's High/Low/Close.

    Output columns (legacy):
      Pivot_P, R1_P, S1_P, R2_P, S2_P, R3_P, S3_P
    """
    if df is None or df.empty:
        return df

    if not all(c in df.columns for c in ["High", "Low", "Close"]):
        for col in ["Pivot_P", "R1_P", "S1_P", "R2_P", "S2_P", "R3_P", "S3_P"]:
            df[col] = np.nan
        return df

    try:
        prev_high = df["High"].shift(1)
        prev_low = df["Low"].shift(1)
        prev_close = df["Close"].shift(1)

        df["Pivot_P"] = (prev_high + prev_low + prev_close) / 3.0
        df["R1_P"] = (2.0 * df["Pivot_P"]) - prev_low
        df["S1_P"] = (2.0 * df["Pivot_P"]) - prev_high
        df["R2_P"] = df["Pivot_P"] + (prev_high - prev_low)
        df["S2_P"] = df["Pivot_P"] - (prev_high - prev_low)
        df["R3_P"] = prev_high + (2.0 * (df["Pivot_P"] - prev_low))
        df["S3_P"] = prev_low - (2.0 * (prev_high - df["Pivot_P"]))

    except Exception as e:
        eprint(f"TI worker: error calculating classic pivots: {e}")
        traceback.print_exc(file=sys.stderr)
        for col in ["Pivot_P", "R1_P", "S1_P", "R2_P", "S2_P", "R3_P", "S3_P"]:
            df[col] = np.nan

    return df


# ----------------------------
# Indicators
# ----------------------------


def add_technical_indicators(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """
    Computes TA indicators using TA-Lib and returns enriched dataframe.

    Keeps legacy naming (after rename pass):
      MA5, MA10, MA20, MA50, MA200,
      RSI (14),
      Stochastic %K, STOCH_%D,
      STOCHRSI_%K, STOCHRSI_%D,
      MACD, MACD_Hist, MACD_Signal,
      ADX (14), ADX_DMP, ADX_DMN,
      CCI (14), ROC (10), ATR (14),
      Ultimate Oscillator, Williams %R,
      BullBear Power,
      Pivot_P, R1_P, S1_P, R2_P, S2_P, R3_P, S3_P
    """
    if df is None or df.empty:
        eprint("TI worker: cannot add indicators - input df is empty.")
        return None

    required = ["Open", "High", "Low", "Close"]
    if not all(c in df.columns for c in required):
        eprint(
            f"TI worker: missing OHLC required for TA: {required}. cols={list(df.columns)}"
        )
        return None

    # Ensure numeric OHLC
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if df[required].isna().all(axis=None):
        eprint("TI worker: OHLC all NaN after numeric coercion.")
        return None

    try:
        import talib  # type: ignore

        enriched = df.copy()

        close = pd.to_numeric(enriched["Close"], errors="coerce").to_numpy(dtype=float)
        high = pd.to_numeric(enriched["High"], errors="coerce").to_numpy(dtype=float)
        low = pd.to_numeric(enriched["Low"], errors="coerce").to_numpy(dtype=float)

        # Trend / moving averages
        enriched["MA5"] = talib.SMA(close, timeperiod=5)
        enriched["MA10"] = talib.SMA(close, timeperiod=10)
        enriched["MA20"] = talib.SMA(close, timeperiod=20)
        enriched["MA50"] = talib.SMA(close, timeperiod=50)
        enriched["MA200"] = talib.SMA(close, timeperiod=200)

        # Oscillators and momentum
        enriched["RSI (14)"] = talib.RSI(close, timeperiod=14)

        stoch_k, stoch_d = talib.STOCH(
            high,
            low,
            close,
            fastk_period=14,
            slowk_period=3,
            slowk_matype=0,
            slowd_period=3,
            slowd_matype=0,
        )
        enriched["Stochastic %K"] = stoch_k
        enriched["STOCH_%D"] = stoch_d

        stochrsi_k, stochrsi_d = talib.STOCHRSI(
            close,
            timeperiod=14,
            fastk_period=3,
            fastd_period=3,
            fastd_matype=0,
        )
        enriched["STOCHRSI_%K"] = stochrsi_k
        enriched["STOCHRSI_%D"] = stochrsi_d

        macd, macd_signal, macd_hist = talib.MACD(
            close,
            fastperiod=12,
            slowperiod=26,
            signalperiod=9,
        )
        enriched["MACD"] = macd
        enriched["MACD_Signal"] = macd_signal
        enriched["MACD_Hist"] = macd_hist

        enriched["ADX (14)"] = talib.ADX(high, low, close, timeperiod=14)
        enriched["ADX_DMP"] = talib.PLUS_DI(high, low, close, timeperiod=14)
        enriched["ADX_DMN"] = talib.MINUS_DI(high, low, close, timeperiod=14)

        enriched["CCI (14)"] = talib.CCI(high, low, close, timeperiod=14)
        enriched["ROC (10)"] = talib.ROC(close, timeperiod=10)
        enriched["ATR (14)"] = talib.ATR(high, low, close, timeperiod=14)
        enriched["Ultimate Oscillator"] = talib.ULTOSC(
            high,
            low,
            close,
            timeperiod1=7,
            timeperiod2=14,
            timeperiod3=28,
        )
        enriched["Williams %R"] = talib.WILLR(high, low, close, timeperiod=14)

        # BullBear Power (elder-ray aggregate): (High-EMA13) + (Low-EMA13)
        ema13 = talib.EMA(close, timeperiod=13)
        enriched["BullBear Power"] = (high - ema13) + (low - ema13)

        # Pivot points
        enriched = calculate_classic_pivot_points(enriched)

        # Post-cleaning: drop rows with NaNs in essential model-readiness columns (legacy logic)
        essential_cols = [
            "Close",
            "Open",
            "High",
            "Low",
            "ATR (14)",
            "RSI (14)",
            "Stochastic %K",
            "STOCH_%D",
            "ADX (14)",
            "CCI (14)",
            "ROC (10)",
            "Ultimate Oscillator",
            "Williams %R",
            "BullBear Power",
            "MA50",
            "MA200",
        ]
        existing_essential = [c for c in essential_cols if c in enriched.columns]

        before = len(enriched)
        if existing_essential:
            enriched = cast(
                pd.DataFrame, enriched.dropna(subset=existing_essential, how="any")
            )
            dropped = before - len(enriched)
            if dropped > 0:
                eprint(
                    f"TI worker: dropped {dropped} rows with NaNs in {len(existing_essential)} essential columns."
                )
        else:
            enriched = cast(pd.DataFrame, enriched.dropna(subset=["Close"], how="any"))

        if enriched.empty:
            eprint("TI worker: data became empty after final dropna post-indicators.")
            return None

        # Legacy minimum requirement (kept)
        min_len = 50
        if len(enriched) < min_len:
            eprint(
                f"TI worker: insufficient data ({len(enriched)} rows) for {ticker} after cleaning. Need at least {min_len}."
            )
            return None

        return enriched

    except Exception as e:
        eprint(f"TI worker: exception during indicator calculation: {e}")
        traceback.print_exc(file=sys.stderr)
        return None


# ----------------------------
# Main entrypoint (worker protocol)
# ----------------------------


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    ticker = _resolve_ticker(args)
    history_mode = str(getattr(args, "history_mode", "live") or "live").strip().lower()
    as_of_date = str(getattr(args, "as_of_date", "") or "").strip()

    if history_mode == "replay" and as_of_date == "":
        eprint(
            "TI worker: --as-of-date is required when --history-mode replay is used."
        )
        return 1

    # Normal run begins here (help mode will already have exited via argparse)
    eprint(f"\n--- Starting TI worker for ticker: {ticker} ---")
    eprint(f"FIN root: {paths.APP_ROOT}")
    eprint(f"Raw dir:  {paths.DATA_TICKERS_DIR} (fallback: {paths.DATA_RAW_DIR})")
    eprint(f"History mode: {history_mode}")
    if history_mode == "replay":
        eprint(f"As-of date: {as_of_date}")

    # Require optional dependency only after parsing args (so --help works without TA-Lib)
    try:
        _require_talib()
    except Exception:
        return 1

    # Use FIN canonical loader (centralized sanitization)
    raw_path = resolve_raw_csv_path(ticker)
    raw_df = fetch_data(
        ticker,
        csv_path=raw_path,
        as_of_date=(as_of_date if history_mode == "replay" else None),
    )

    if raw_df is None or raw_df.empty:
        eprint("TI worker: failed to load/process initial data. Aborting.")
        return 1

    # Enforce business-day frequency for consistent indicators
    raw_df_b = ensure_business_day_ohlc(raw_df)
    if raw_df_b is None or raw_df_b.empty:
        eprint("TI worker: failed to regularize business-day OHLC. Aborting.")
        return 1

    enriched = add_technical_indicators(raw_df_b, ticker)
    if enriched is None or enriched.empty:
        eprint(
            "TI worker: failed to calculate indicators or data became empty. Aborting."
        )
        return 1

    # Write temp file and print path to stdout
    temp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as tmp:
            temp_path = tmp.name
            enriched.to_csv(tmp, index=True, date_format="%Y-%m-%d")

        print(temp_path, flush=True)
        eprint(f"--- TI worker: enriched data saved to {temp_path}. ---")
        return 0

    except Exception as e:
        eprint(f"TI worker: error writing to temp file: {e}")
        traceback.print_exc(file=sys.stderr)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as rm_err:
                eprint(
                    f"TI worker: warning - could not remove temp file {temp_path}: {rm_err}"
                )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
