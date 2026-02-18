# ------------------------
# scripts/workers/app3GPC.py
# ------------------------
"""
FIN Torch Forecasting Worker (subprocess)

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
- Keep output schema compatible with table/plot consumers:
    index = future business dates (B)
    columns = TorchForecast_Pred, TorchForecast_Lower, TorchForecast_Upper

Notes
-----
- pytorch-forecasting is an optional dependency.
- Help mode (--help) succeeds even if pytorch-forecasting is missing.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import traceback
import warnings
from pathlib import Path
from typing import Any, Optional, Tuple, cast

import numpy as np
import pandas as pd


# ----------------------------
# Environment tuning
# ----------------------------

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
    app_root = scripts_dir.parent

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
FORECAST_HORIZON = int(os.environ.get("FIN_FH", "3"))
PREDICTION_COVERAGE = float(os.environ.get("FIN_TF_COVERAGE", "0.90"))


# ----------------------------
# CLI
# ----------------------------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="app3GPC.py",
        description="FIN torch-forecasting worker (writes temp CSV path to stdout; diagnostics on stderr).",
    )
    p.add_argument(
        "ticker",
        nargs="?",
        default=None,
        help="Ticker symbol (legacy positional). Example: AAPL",
    )
    p.add_argument(
        "--ticker",
        dest="ticker_flag",
        default=None,
        help="Ticker symbol (explicit form). If provided, overrides positional ticker.",
    )
    return p.parse_args(argv)


def _resolve_ticker(args: argparse.Namespace) -> str:
    if getattr(args, "ticker_flag", None):
        return str(args.ticker_flag)
    if getattr(args, "ticker", None):
        return str(args.ticker)
    return DEFAULT_TICKER


# ----------------------------
# Optional dependency import (pytorch-forecasting)
# ----------------------------


def _import_torch_forecasting() -> Tuple[Any, Any]:
    try:
        from pytorch_forecasting import Baseline, TimeSeriesDataSet  # type: ignore

        return Baseline, TimeSeriesDataSet
    except Exception as e:
        eprint("pytorch-forecasting is not available in this environment.")
        eprint("Install (example): pip install pytorch-forecasting")
        eprint(f"Import error: {e}")
        raise


# ----------------------------
# Data prep
# ----------------------------


def fetch_minimal_data(ticker: str) -> Optional[pd.DataFrame]:
    try:
        eprint(f"TorchForecast worker: resolving FIN raw CSV for {ticker}...")
        raw_path = paths.DATA_RAW_DIR / f"{ticker.replace('^', '')}_data.csv"
        eprint(f"TorchForecast worker: expected path: {raw_path}")

        df_full = fetch_data(ticker, csv_path=raw_path)
        if df_full is None or df_full.empty:
            eprint("TorchForecast worker: fetch_data() returned no data.")
            return None

        if TARGET_COLUMN not in df_full.columns:
            eprint(
                f"TorchForecast worker: required column '{TARGET_COLUMN}' not found. "
                f"Columns={list(df_full.columns)}"
            )
            return None

        data_df = cast(pd.DataFrame, df_full[[TARGET_COLUMN]].copy())
        data_df[TARGET_COLUMN] = pd.to_numeric(data_df[TARGET_COLUMN], errors="coerce")
        data_df = cast(pd.DataFrame, data_df.dropna(subset=[TARGET_COLUMN]))
        data_df = cast(pd.DataFrame, data_df.asfreq("B", method="ffill"))

        min_required_len = (3 * int(FORECAST_HORIZON)) + 20
        if len(data_df) < min_required_len:
            eprint(
                f"TorchForecast worker: insufficient data length ({len(data_df)}). "
                f"Need at least {min_required_len}."
            )
            return None

        return data_df
    except Exception as e:
        eprint(f"TorchForecast worker: data prep failed for {ticker}: {e}")
        traceback.print_exc(file=sys.stderr)
        return None


def _future_bdays(last_date: pd.Timestamp, fh: int) -> pd.DatetimeIndex:
    return pd.date_range(
        start=last_date + pd.offsets.BDay(1), periods=int(fh), freq="B"
    )


def _safe_sigma(series: pd.Series) -> float:
    d = cast(pd.Series, pd.to_numeric(series, errors="coerce")).diff().dropna()
    sigma = float(np.nanstd(d.to_numpy(dtype=float), ddof=1)) if len(d) > 2 else 0.0
    if not np.isfinite(sigma) or sigma <= 0.0:
        last = float(cast(Any, series.iloc[-1]))
        sigma = max(abs(last) * 0.01, 1e-6)
    return sigma


def run_torch_forecast(
    Baseline: Any,
    TimeSeriesDataSet: Any,
    data: pd.DataFrame,
    target_column: str = TARGET_COLUMN,
    fh: int = FORECAST_HORIZON,
) -> Optional[pd.DataFrame]:
    if data is None or data.empty:
        return None

    y = cast(pd.Series, pd.to_numeric(data[target_column], errors="coerce")).dropna()
    if y.empty:
        return None

    fh_i = int(fh)
    last_dt = cast(pd.Timestamp, pd.Timestamp(cast(Any, y.index.max())))
    future_idx = _future_bdays(last_dt, fh_i)

    try:
        ts = pd.DataFrame({"Date": y.index, "y": y.to_numpy(dtype=float)})
        ts["Date"] = pd.to_datetime(ts["Date"], errors="coerce")
        ts = cast(pd.DataFrame, ts.dropna(subset=["Date", "y"]))
        ts = cast(pd.DataFrame, ts.sort_values("Date"))
        ts["group_id"] = "GLOBAL"
        ts["time_idx"] = np.arange(len(ts), dtype=int)

        max_pred = fh_i
        max_enc = max(12, min(90, int(len(ts) - max_pred)))
        if max_enc <= 0 or len(ts) < (max_pred + 12):
            raise RuntimeError("insufficient rows for TimeSeriesDataSet baseline")

        training = TimeSeriesDataSet(
            ts,
            time_idx="time_idx",
            target="y",
            group_ids=["group_id"],
            max_encoder_length=max_enc,
            max_prediction_length=max_pred,
            time_varying_unknown_reals=["y"],
            allow_missing_timesteps=True,
        )
        predict_ds = TimeSeriesDataSet.from_dataset(
            training,
            ts,
            predict=True,
            stop_randomization=True,
        )
        predict_dl = predict_ds.to_dataloader(train=False, batch_size=1, num_workers=0)

        baseline = Baseline()
        pred_raw = baseline.predict(predict_dl)
        if hasattr(pred_raw, "detach"):
            arr = np.asarray(pred_raw.detach().cpu().numpy(), dtype=float)
        else:
            arr = np.asarray(pred_raw, dtype=float)

        point = arr.reshape(-1)
        if point.size == 0:
            raise RuntimeError("empty forecast from Baseline.predict")

        if point.size < fh_i:
            pad = np.full((fh_i - point.size,), point[-1], dtype=float)
            point = np.concatenate([point, pad])
        point = point[:fh_i]

    except Exception as e:
        eprint(
            "TorchForecast worker: pytorch-forecasting path failed; "
            f"falling back to naive repeat. Error: {e}"
        )
        point = np.full((fh_i,), float(y.iloc[-1]), dtype=float)

    sigma = _safe_sigma(y)
    z = 1.645 if 0.5 < float(PREDICTION_COVERAGE) < 0.999 else 1.645
    lower = point - z * sigma
    upper = point + z * sigma

    return pd.DataFrame(
        {
            "TorchForecast_Pred": point,
            "TorchForecast_Lower": lower,
            "TorchForecast_Upper": upper,
        },
        index=future_idx,
    )


# ----------------------------
# Main entrypoint
# ----------------------------


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    ticker_arg = _resolve_ticker(args)

    eprint(f"--- Starting TorchForecast worker for ticker: {ticker_arg} ---")
    eprint(f"FIN root: {paths.APP_ROOT}")
    eprint(f"Raw dir:  {paths.DATA_RAW_DIR}")
    eprint(f"FH:       {FORECAST_HORIZON}")

    try:
        Baseline, TimeSeriesDataSet = _import_torch_forecasting()
    except Exception:
        return 1

    stock_data = fetch_minimal_data(ticker_arg)
    if stock_data is None:
        eprint("TorchForecast worker: data preparation failed.")
        return 1

    forecast_df = run_torch_forecast(Baseline, TimeSeriesDataSet, stock_data)
    if forecast_df is None or forecast_df.empty:
        eprint("TorchForecast worker: forecasting failed or returned no results.")
        return 1

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as temp_f:
            forecast_df.to_csv(temp_f, index=True, date_format="%Y-%m-%d")
            print(temp_f.name, flush=True)

        eprint("--- TorchForecast worker: results saved; temp path sent to stdout. ---")
        return 0
    except Exception as write_err:
        eprint(f"TorchForecast worker: error writing results to temp file: {write_err}")
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
