# ------------------------
# scripts\workers\app3GPC.py
# ------------------------
"""
FIN PyCaret Forecasting Worker (subprocess)

Contract with main orchestrator (Models.run_external_script)
-----------------------------------------------------------
- Invoked as:  python app3GPC.py <TICKER>
- Writes forecast results to a temporary CSV file
- Prints the temp CSV path to STDOUT (single line)
- All diagnostics go to STDERR
- Exit code 0 on success, non-zero on failure

FIN integration goals
---------------------
- No hardcoded absolute paths
- Use FIN path layer (src.config.paths) and FIN loader (src.data.loading.fetch_data)
- Robust sys.path bootstrap when executed from scripts/workers
- Keep output schema compatible with legacy plotting/aggregation:
    index = future business dates (B)
    columns = PyCaret_Pred, PyCaret_Lower, PyCaret_Upper

Notes
-----
- PyCaret is an optional dependency. If missing, the worker fails fast (on normal runs).
- Help mode (--help) must succeed even if PyCaret is missing.
- Business-day frequency is enforced for the series passed to PyCaret.
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


# ----------------------------
# Environment tuning (quiet PyCaret)
# ----------------------------

os.environ.setdefault("PYCARET_CUSTOM_LOGGING_LEVEL", "CRITICAL")
os.environ.setdefault("LIGHTGBM_VERBOSE", "-1")
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
    """
    Resolve FIN root from scripts/workers and ensure:
      - FIN root on sys.path => import src.*
      - (optional) compat on sys.path if needed later
    """
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
    from src.data.loading import fetch_data
except Exception as e:
    raise RuntimeError(
        "Failed to import FIN loader: from src.data.loading import fetch_data. "
        "Ensure src/data/loading.py exists."
    ) from e


# ----------------------------
# Configuration
# ----------------------------

DEFAULT_TICKER = "AAPL"
TARGET_COLUMN = "Close"

# Prefer runtime override via environment, else default to 3
FORECAST_HORIZON = int(os.environ.get("FIN_FH", "3"))

# Prediction interval coverage (0.90 => 90% PI). Override via env if desired.
PREDICTION_COVERAGE = float(os.environ.get("FIN_PYCARET_COVERAGE", "0.9"))


# ----------------------------
# CLI
# ----------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Legacy contract: python app3GPC.py <TICKER>
    Also supports:  python app3GPC.py --ticker <TICKER>
    """
    p = argparse.ArgumentParser(
        prog="app3GPC.py",
        description="FIN PyCaret forecasting worker (writes temp CSV path to stdout; diagnostics on stderr).",
    )

    # Backward-compatible positional ticker:
    p.add_argument(
        "ticker",
        nargs="?",
        default=None,
        help="Ticker symbol (legacy positional). Example: AAPL",
    )

    # Optional explicit flag (does not break legacy):
    p.add_argument(
        "--ticker",
        dest="ticker_flag",
        default=None,
        help="Ticker symbol (explicit form). If provided, overrides positional ticker.",
    )

    return p.parse_args(argv)


def _resolve_ticker(args: argparse.Namespace) -> str:
    # Flag form overrides positional to be explicit and deterministic.
    if getattr(args, "ticker_flag", None):
        return str(args.ticker_flag)
    if getattr(args, "ticker", None):
        return str(args.ticker)
    return DEFAULT_TICKER


# ----------------------------
# Optional dependency import (PyCaret) — deferred so --help works without PyCaret
# ----------------------------

def _import_pycaret() -> "type[object]":
    try:
        from pycaret.time_series import TSForecastingExperiment  # type: ignore
        return TSForecastingExperiment
    except Exception as e:
        eprint("PyCaret is not available in this environment.")
        eprint("Install/enable it (example): pip install pycaret")
        eprint(f"Import error: {e}")
        raise


# ----------------------------
# Data prep (FIN canonical)
# ----------------------------

def fetch_minimal_data(ticker: str) -> Optional[pd.DataFrame]:
    """
    Load and minimally prepare a target series for PyCaret:
      - Use FIN canonical loader on data/raw/{TICKER}_data.csv
      - Select Close
      - Force business-day frequency and forward-fill
      - Validate minimum length
    Returns DataFrame with DatetimeIndex and one column TARGET_COLUMN.
    """
    try:
        eprint(f"PyCaret worker: resolving FIN raw CSV for {ticker}...")
        raw_path = paths.DATA_RAW_DIR / f"{ticker.replace('^', '')}_data.csv"
        eprint(f"PyCaret worker: expected path: {raw_path}")

        df_full = fetch_data(ticker, csv_path=raw_path)
        if df_full is None or df_full.empty:
            eprint("PyCaret worker: fetch_data() returned no data.")
            return None

        if TARGET_COLUMN not in df_full.columns:
            eprint(f"PyCaret worker: required column '{TARGET_COLUMN}' not found. Columns={list(df_full.columns)}")
            return None

        data_df = cast(pd.DataFrame, df_full[[TARGET_COLUMN]].copy())
        data_df[TARGET_COLUMN] = pd.to_numeric(data_df[TARGET_COLUMN], errors="coerce")
        data_df = cast(pd.DataFrame, data_df.dropna(subset=[TARGET_COLUMN]))

        if data_df.empty:
            eprint("PyCaret worker: Close series empty after numeric coercion/dropna.")
            return None

        # Force business-day frequency (PyCaret TS expects regular freq for many models)
        data_df = cast(pd.DataFrame, data_df.asfreq("B", method="ffill"))

        min_required_len = (3 * int(FORECAST_HORIZON)) + 15
        if len(data_df) < min_required_len:
            eprint(
                f"PyCaret worker: insufficient data length ({len(data_df)}). "
                f"Need at least {min_required_len}."
            )
            return None

        return data_df

    except Exception as e:
        eprint(f"PyCaret worker: error while loading/processing data for {ticker}: {e}")
        traceback.print_exc(file=sys.stderr)
        return None


# ----------------------------
# Forecasting
# ----------------------------

def run_pycaret_forecast(
    TSForecastingExperiment: type,  # injected to avoid import-time dependency
    data: pd.DataFrame,
    target_column: str = TARGET_COLUMN,
    fh: int = FORECAST_HORIZON,
) -> Optional[pd.DataFrame]:
    """
    Run PyCaret TS experiment and return DataFrame with:
      - PyCaret_Pred
      - PyCaret_Lower
      - PyCaret_Upper
    Index: forecast horizon business dates (as returned by PyCaret).
    """
    if data is None or data.empty:
        eprint("PyCaret worker: cannot run forecast on empty data.")
        return None

    eprint("\n--- Starting PyCaret Forecasting Process ---")
    try:
        exp = TSForecastingExperiment()
        exp.setup(
            data=data,
            target=target_column,
            fh=int(fh),
            fold=3,
            session_id=123,
            numeric_imputation_target="ffill",
            verbose=False,
        )

        best_model = exp.compare_models(sort="MAE", verbose=False, n_select=1)
        if best_model is None:
            eprint("PyCaret worker: compare_models returned None.")
            return None

        final_model = exp.finalize_model(best_model)

        # Attempt prediction intervals, fall back to point forecast.
        try:
            eprint(f"Attempting to predict with intervals (coverage={PREDICTION_COVERAGE})...")
            predictions = exp.predict_model(
                final_model,
                return_pred_int=True,
                alpha=1.0 - float(PREDICTION_COVERAGE),
            )
            eprint("Prediction with intervals successful.")
        except Exception as e_int:
            eprint(
                "Warning: could not get prediction intervals. "
                "The selected model may not support them."
            )
            eprint(f"Interval error: {e_int}")
            eprint("Falling back to point forecast...")
            predictions = exp.predict_model(final_model)
            eprint("Point forecast successful.")

        if predictions is None or predictions.empty:
            eprint("PyCaret worker: predict_model returned empty DataFrame.")
            return None

        # Normalize expected output columns
        preds = predictions.copy()
        rename_map = {"y_pred": "PyCaret_Pred"}

        # PyCaret interval column names vary by version; handle common patterns.
        cov = str(PREDICTION_COVERAGE)
        candidates_lower = [
            f"y_pred_lower_{cov}",
            f"y_pred_lower_{PREDICTION_COVERAGE}",
            "y_pred_lower",
        ]
        candidates_upper = [
            f"y_pred_upper_{cov}",
            f"y_pred_upper_{PREDICTION_COVERAGE}",
            "y_pred_upper",
        ]

        lower_found = next((c for c in candidates_lower if c in preds.columns), None)
        upper_found = next((c for c in candidates_upper if c in preds.columns), None)

        if lower_found:
            rename_map[lower_found] = "PyCaret_Lower"
        if upper_found:
            rename_map[upper_found] = "PyCaret_Upper"

        preds.rename(columns=rename_map, inplace=True)

        # Ensure all 3 columns exist
        output_cols = ["PyCaret_Pred", "PyCaret_Lower", "PyCaret_Upper"]
        for col in output_cols:
            if col not in preds.columns:
                preds[col] = np.nan

        output_df = cast(pd.DataFrame, preds[output_cols].copy())

        # Enforce numeric dtype where possible
        for col in output_cols:
            output_df[col] = pd.to_numeric(output_df[col], errors="coerce")

        eprint(f"Prepared output DataFrame. Shape: {output_df.shape}")
        return output_df

    except Exception as e:
        eprint(f"PyCaret worker: unhandled forecasting error: {e}")
        traceback.print_exc(file=sys.stderr)
        return None


# ----------------------------
# Main entrypoint (worker protocol)
# ----------------------------

def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    ticker_arg = _resolve_ticker(args)

    # Normal run begins here (help mode will already have exited via argparse)
    eprint(f"--- Starting PyCaret worker for ticker: {ticker_arg} ---")
    eprint(f"FIN root: {paths.APP_ROOT}")
    eprint(f"Raw dir:  {paths.DATA_RAW_DIR}")
    eprint(f"FH:       {FORECAST_HORIZON}")

    # Import optional dependency only after parsing args (so --help works without pycaret)
    try:
        TSForecastingExperiment = _import_pycaret()
    except Exception:
        return 1

    stock_data_for_pycaret = fetch_minimal_data(ticker_arg)
    if stock_data_for_pycaret is None:
        eprint("PyCaret worker: data preparation failed.")
        return 1

    forecast_results_df = run_pycaret_forecast(TSForecastingExperiment, stock_data_for_pycaret)
    if forecast_results_df is None or forecast_results_df.empty:
        eprint("PyCaret worker: forecasting failed or returned no results.")
        return 1

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as temp_f:
            forecast_results_df.to_csv(temp_f, index=True, date_format="%Y-%m-%d")
            # Communication channel back to main app: print the temp file path to stdout
            print(temp_f.name, flush=True)

        eprint("--- PyCaret worker: results saved; temp path sent to stdout. ---")
        return 0

    except Exception as write_err:
        eprint(f"PyCaret worker: error writing results to temp file: {write_err}")
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
