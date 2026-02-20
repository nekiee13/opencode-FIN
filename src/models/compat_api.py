# ------------------------
# src/models/compat_api.py
# ------------------------
"""
Canonical legacy-API model functions migrated out of compat/Models.py.

Purpose
-------
Phase-1 Path Stabilization:
- src/ is canonical implementation
- compat/ is delegation-only shim

This module intentionally preserves the legacy public API:
- function names
- signatures
- return shapes
- optional-dependency behavior (lazy imports)

Important invariants
--------------------
- This module must be import-safe in minimal environments.
  Therefore, legacy/optional modules (e.g., compat.ExoConfig, compat.PCEModel)
  are imported locally inside the functions that actually use them.
- Optional heavy dependencies (torch, tensorflow-legacy, sklearn, pmdarima, statsmodels, arch)
  remain imported lazily inside the corresponding functions.

Notes
-----
- This module still references legacy config/constants under compat/ to preserve
  behavior during Phase-1. Long-term, migrate these into src/ and update call sites.

Debug/Temp policy (Phase-1 addendum)
------------------------------------
- FIN_KEEP_TEMP=1 disables deletion of temp artifacts created/handled here.
- FIN_DEBUG_DIR, if set, is used as a stable debug artifact root; otherwise:
  <repo_root>/debug_artifacts is used.
- External workers (TI/TorchForecast) still create their temp CSV in OS temp; however:
  when FIN_DEBUG_DIR is enabled, the returned CSV is copied into debug artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Tuple, cast

# Soft imports for numpy/pandas to avoid hard-crash at import time in minimal envs.
try:  # pragma: no cover
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:  # pragma: no cover
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

from src.config import paths
from src.utils import compat as opt

from compat import Constants as C

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from pandas import DataFrame, Index, Series

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Debug/temp helpers
# ----------------------------------------------------------------------


def _truthy_env(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _repo_root_from_here() -> "Path":
    """
    src/models/compat_api.py -> src/models -> src -> repo root
    """
    return Path(__file__).resolve().parents[2]


def _debug_root_dir() -> "Path":
    """
    Debug root directory resolution.

    Priority:
    1) FIN_DEBUG_DIR env var
    2) <repo_root>/debug_artifacts
    """
    env = os.environ.get("FIN_DEBUG_DIR", "").strip()
    if env:
        return Path(env)
    return _repo_root_from_here() / "debug_artifacts"


def _ensure_dir(p: "Path") -> "Path":
    p.mkdir(parents=True, exist_ok=True)
    return p


def _make_work_dir(prefix: str) -> Tuple["Path", bool]:
    """
    Create a work directory.

    If FIN_KEEP_TEMP=1, creates under <debug_root>/temp and returns keep=True.
    Else uses OS temp and returns keep=False.
    """
    keep = _truthy_env("FIN_KEEP_TEMP")
    if keep:
        base = _ensure_dir(_debug_root_dir() / "temp")
        wd = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))
        return wd, True

    wd = Path(tempfile.mkdtemp(prefix=prefix))
    return wd, False


def _copy_to_debug(src_path: str, *, tag: str) -> Optional[str]:
    """
    Copy a file into debug artifacts when FIN_DEBUG_DIR is set (or default debug root exists).
    Returns copied path or None.
    """
    try:
        src = Path(src_path)
        if not src.exists():
            return None

        # Always allow copying when FIN_DEBUG_DIR is set OR FIN_KEEP_TEMP is enabled.
        if not (
            _truthy_env("FIN_KEEP_TEMP") or os.environ.get("FIN_DEBUG_DIR", "").strip()
        ):
            return None

        dst_dir = _ensure_dir(_debug_root_dir() / tag)
        dst = dst_dir / src.name
        shutil.copy2(str(src), str(dst))
        return str(dst)
    except Exception as e:
        log.info("Debug copy skipped/failed for %s: %s", src_path, e)
        return None


# ----------------------------------------------------------------------
# PCE worker interpreter resolution (env → Constants → candidates)
# ----------------------------------------------------------------------


def _resolve_pce_worker_python() -> str:
    """
    Resolve the PCE worker interpreter path robustly on Windows.

    Priority:
    1) FIN_PCE_PY_EXE environment variable (must exist)
    2) compat.Constants.PCE_WORKER_PY_EXE (must exist)
    3) Known FIN_PCE layouts:
       - F:\\vEnv\\FIN_PCE\\python.exe            (observed in this project)
       - F:\\vEnv\\FIN_PCE\\Scripts\\python.exe   (standard venv layout)
    """
    env = os.environ.get("FIN_PCE_PY_EXE", "").strip()
    if env and os.path.exists(env):
        return env

    try:
        override = str(getattr(C, "PCE_WORKER_PY_EXE", "")).strip()
        if override and os.path.exists(override):
            return override
    except Exception:
        pass

    candidates = [
        r"F:\vEnv\FIN_PCE\python.exe",
        r"F:\vEnv\FIN_PCE\Scripts\python.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    # Last-resort: return the first candidate (caller will log a clear error).
    return candidates[0]


PCE_WORKER_PY_EXE = _resolve_pce_worker_python()

# ======================================================================
# External script runners (legacy contract: stdout prints temp CSV path)
# ======================================================================


def run_external_script(
    script_name: str,
    ticker: str,
    timeout: int,
    progress_callback=None,
) -> Optional["DataFrame"]:
    """Run an external Python script and return a DataFrame loaded from its temp CSV.

    Contract (legacy):
    - Worker prints a temp CSV path to stdout.
    - Caller reads it and removes the file.

    Debug policy:
    - If FIN_DEBUG_DIR is set (or FIN_KEEP_TEMP=1), the temp CSV is copied to:
      <debug_root>/external_workers/<filename>.csv
    - If FIN_KEEP_TEMP=1, the original temp CSV is NOT deleted.
    """
    if pd is None:
        log.error("pandas is not available; cannot run external script workflows.")
        return None

    try:
        script_path = paths.get_worker_script_path(script_name)
    except FileNotFoundError:
        log.error("External script not found: %s", script_name)
        return None

    python_executable = sys.executable
    temp_file_path: Optional[str] = None

    log.info(
        "Running external script '%s' (resolved: %s) in directory '%s'",
        script_name,
        script_path,
        paths.APP_ROOT,
    )

    try:
        process = subprocess.run(
            [python_executable, str(script_path), ticker],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            cwd=str(paths.APP_ROOT),
        )

        if process.stderr:
            log.info("--- %s stderr for %s ---", script_name, ticker)
            for line in process.stderr.strip().split("\n"):
                if line.strip():
                    log.info("[%s] %s", script_name, line.strip())
            log.info("--- End %s stderr ---", script_name)

        if process.returncode != 0:
            log.error(
                "External script %s failed for %s (exit code %s).",
                script_name,
                ticker,
                process.returncode,
            )
            log.error("stderr: %s", (process.stderr or "").strip())
            return None

        stdout_lines = [
            line for line in (process.stdout or "").strip().split("\n") if line.strip()
        ]
        extracted_path: Optional[str] = None

        for line in reversed(stdout_lines):
            candidate = line.strip().strip('"').strip("'")
            if candidate.lower().endswith(".csv") and os.path.exists(candidate):
                extracted_path = candidate
                log.info(
                    "Successfully extracted and validated temp file path: %s",
                    extracted_path,
                )
                break

        if not extracted_path:
            log.error(
                "Could not find a valid .csv path in stdout from %s for %s.",
                script_name,
                ticker,
            )
            if stdout_lines:
                log.info("stdout (tail): %s", " | ".join(stdout_lines[-5:]))
            return None

        temp_file_path = extracted_path

        # Copy to debug artifacts if configured.
        copied = _copy_to_debug(temp_file_path, tag="external_workers")
        if copied:
            log.info("Copied worker CSV to debug artifacts: %s", copied)

        df_out: "DataFrame" = pd.read_csv(temp_file_path, index_col=0, parse_dates=True)
        return df_out

    except Exception as e:
        log.error(
            "Error processing external script %s results for %s: %s",
            script_name,
            ticker,
            e,
            exc_info=True,
        )
        return None

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            if _truthy_env("FIN_KEEP_TEMP"):
                log.info("FIN_KEEP_TEMP=1: keeping temp file: %s", temp_file_path)
            else:
                try:
                    os.remove(temp_file_path)
                    log.info("Cleaned up temporary file: %s", temp_file_path)
                except OSError as remove_err:
                    log.warning(
                        "Could not remove temporary file %s: %s",
                        temp_file_path,
                        remove_err,
                    )


def run_external_ti_calculator(
    ticker: str,
    progress_callback=None,
) -> Optional["DataFrame"]:
    """Run TI worker and return enriched DataFrame."""
    if pd is None:
        return None

    enriched_df = run_external_script("app3GTI.py", ticker, 120, progress_callback)
    if enriched_df is None:
        return None

    index_freq = getattr(enriched_df.index, "freq", None)
    if index_freq is None:
        enriched_df = cast("DataFrame", enriched_df.asfreq("B").ffill())
        essential_cols = ["Open", "High", "Low", "Close", "ATR (14)"]
        cols_present = [c for c in essential_cols if c in enriched_df.columns]
        enriched_df.dropna(subset=cols_present, inplace=True)
        if enriched_df.empty:
            log.warning("Enriched TI data became empty after asfreq/ffill/dropna.")
            return None

    return enriched_df


def run_external_torch_forecasting(
    ticker: str,
    progress_callback=None,
) -> Optional["DataFrame"]:
    """Run torch-forecasting worker."""
    return run_external_script("app3GPC.py", ticker, 600, progress_callback)


# ======================================================================
# PCE external worker helpers (NumPy 2.x isolation)
# ======================================================================


def _pce_worker_script_path() -> "Path":
    """
    Canonical worker location:
      repo_root/scripts/workers/pce_worker.py
    """
    return _repo_root_from_here() / "scripts" / "workers" / "pce_worker.py"


def _write_df_csv_for_worker(df: "DataFrame", out_path: str) -> None:
    if pd is None:
        raise RuntimeError("pandas is required to serialize worker inputs.")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    df2 = df.copy()
    if isinstance(df2.index, pd.DatetimeIndex):
        df2.index.name = "Date"
        df2.reset_index().to_csv(out_path, index=False)
    else:
        df2.to_csv(out_path, index=False)


def _read_forecast_csv(path: str) -> "DataFrame":
    if pd is None:
        raise RuntimeError("pandas is required to read worker outputs.")
    df = pd.read_csv(path)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).set_index("Date")
    df.index = pd.to_datetime(df.index, errors="coerce")
    df = cast("DataFrame", df.sort_index())
    return df


def _run_pce_worker(
    enriched_data: "DataFrame",
    exog_train_df: Optional["DataFrame"],
    exog_future_df: Optional["DataFrame"],
    *,
    ticker: str,
) -> Optional["DataFrame"]:
    """
    Run PCE-NARX in the dedicated NumPy-2 environment and return the forecast DataFrame.

    Temp policy:
    - If FIN_KEEP_TEMP=1: all worker IO stays under <debug_root>/temp/fin_pce_* and is kept.
    - Else: OS temp is used and the folder is deleted at the end.
    - If FIN_DEBUG_DIR is set (or FIN_KEEP_TEMP=1): input/output JSON and CSVs are retained
      (kept by directory policy) and forecast CSV is also copied into <debug_root>/pce_worker/.
    """
    if pd is None:
        return None

    worker_py = PCE_WORKER_PY_EXE
    worker_script = _pce_worker_script_path()

    if not os.path.exists(worker_py):
        log.error("PCE worker python not found: %s", worker_py)
        return None
    if not worker_script.exists():
        log.error("PCE worker script not found: %s", worker_script)
        return None

    work_dir, keep = _make_work_dir(prefix="fin_pce_")
    try:
        td_path = work_dir
        in_json = str(td_path / "pce_in.json")
        out_json = str(td_path / "pce_out.json")

        enriched_csv = str(td_path / "enriched.csv")
        _write_df_csv_for_worker(enriched_data, enriched_csv)

        ex_train_csv: Optional[str] = None
        if exog_train_df is not None and not exog_train_df.empty:
            ex_train_csv = str(td_path / "exog_train.csv")
            _write_df_csv_for_worker(exog_train_df, ex_train_csv)

        ex_future_csv: Optional[str] = None
        if exog_future_df is not None and not exog_future_df.empty:
            ex_future_csv = str(td_path / "exog_future.csv")
            _write_df_csv_for_worker(exog_future_df, ex_future_csv)

        forecast_out = str(td_path / "pce_forecast.csv")

        payload: Dict[str, Any] = {
            "enriched_data_csv": enriched_csv,
            "exog_train_csv": ex_train_csv,
            "exog_future_csv": ex_future_csv,
            "ticker": ticker,
            "target_col": None,
            "fh": int(getattr(C, "FH", 3)),
            "forecast_csv_out": forecast_out,
        }

        with open(in_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        proc = subprocess.run(
            [worker_py, str(worker_script), "--in", in_json, "--out", out_json],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(paths.APP_ROOT),
        )

        if proc.stderr:
            log.info(
                "PCE worker stderr (tail): %s", (proc.stderr or "").strip()[-2000:]
            )

        if not os.path.exists(out_json):
            log.error("PCE worker produced no output JSON. rc=%s", proc.returncode)
            return None

        try:
            with open(out_json, "r", encoding="utf-8") as f:
                result = json.load(f)
        except Exception as e:
            log.error("PCE worker output JSON parse failed: %s", e)
            return None

        if str(result.get("status")) != "OK":
            log.warning(
                "PCE worker status=%s error=%s",
                result.get("status"),
                result.get("error"),
            )
            return None

        forecast_csv = str(result.get("forecast_csv") or "")
        if not forecast_csv or not os.path.exists(forecast_csv):
            log.error("PCE worker forecast CSV missing: %s", forecast_csv)
            return None

        # Copy forecast CSV to a stable location for debugging when enabled.
        copied = _copy_to_debug(forecast_csv, tag="pce_worker")
        if copied:
            log.info("Copied PCE forecast CSV to debug artifacts: %s", copied)

        df = _read_forecast_csv(forecast_csv)

        required_cols = ["PCE_Pred", "PCE_Lower", "PCE_Upper"]
        for c_req in required_cols:
            if c_req not in df.columns:
                log.error("PCE worker output missing column: %s", c_req)
                return None

        if not isinstance(df.index, pd.DatetimeIndex):
            log.error("PCE worker output index is not DatetimeIndex.")
            return None

        return cast("DataFrame", df)

    finally:
        if keep:
            log.info("FIN_KEEP_TEMP=1: keeping PCE work dir: %s", str(work_dir))
        else:
            shutil.rmtree(str(work_dir), ignore_errors=True)


# ======================================================================
# Exogenous matrix builder (shared by ARIMAX, GARCH, LSTM, PCE)
# ======================================================================


def build_exog_matrices(
    model_name: str,
    ticker: str,
    enriched_data: "DataFrame",
    target_index: "Index",
    future_dates: "Index",
    exo_config: Any,
) -> Tuple[Optional["DataFrame"], Optional["DataFrame"]]:
    """Construct X_train and X_future using ExoConfig (legacy behavior)."""
    if pd is None or np is None:
        return None, None

    # Local import to keep module import-safe.
    from compat import ExoConfig  # type: ignore

    regressors: List[str] = ExoConfig.get_enabled_regressors(
        exo_config, model_name, ticker
    )

    if not regressors:
        log.info(
            "No enabled exogenous regressors for model=%s, ticker=%s.",
            model_name,
            ticker,
        )
        return None, None

    valid_regs: List[str] = []
    for reg in regressors:
        if reg in enriched_data.columns:
            valid_regs.append(reg)
        else:
            log.warning(
                "Regressor '%s' for %s/%s not found in enriched_data. Skipping.",
                reg,
                model_name,
                ticker,
            )

    if not valid_regs:
        log.warning(
            "All enabled regressors for %s/%s are missing from data. No exogenous matrix will be used.",
            model_name,
            ticker,
        )
        return None, None

    X_full = cast("DataFrame", enriched_data.loc[:, valid_regs].copy())

    X_train_df = cast("DataFrame", X_full.reindex(index=target_index))
    X_train_df = cast("DataFrame", X_train_df.dropna(how="all"))

    if X_train_df.empty:
        log.warning(
            "X_train for %s/%s is empty after aligning with target_index.",
            model_name,
            ticker,
        )
        return None, None

    horizon: int = int(len(future_dates))
    future_series: Dict[str, "Series"] = {}

    for reg in valid_regs:
        cfg = ExoConfig.get_exog_config(exo_config, model_name, ticker, reg)
        if cfg is None:
            scenario_mode: str = "NONE"
            scenario_values: List[Any] = []
        else:
            scenario_mode = str(cfg.get("scenario_mode", "NONE")).upper()
            scenario_values = list(cfg.get("values", []))

        last_series_any = X_full[reg].reindex(target_index)
        last_series = cast("Series", cast("Series", last_series_any).dropna())
        if last_series.empty:
            last_series_any2 = X_full[reg].dropna()
            last_series = cast("Series", last_series_any2)

        if last_series.empty:
            log.warning(
                "No non-NaN historical values for regressor %s (%s/%s). Using 0.0.",
                reg,
                model_name,
                ticker,
            )
            last_value: float = 0.0
        else:
            last_value = float(last_series.iloc[-1])

        if scenario_mode == "NONE":
            future_vals = np.full(horizon, last_value, dtype=float)

        elif scenario_mode == "DELTA":
            raw_deltas = scenario_values[:horizon]
            if len(raw_deltas) < horizon:
                raw_deltas += [0.0] * (horizon - len(raw_deltas))

            deltas: List[float] = []
            for v in raw_deltas:
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    deltas.append(0.0)
                else:
                    deltas.append(float(v))

            cumulative = np.cumsum(deltas)
            future_vals = last_value + cumulative

        elif scenario_mode == "ABS":
            raw_abs = scenario_values[:horizon]
            if len(raw_abs) < horizon:
                last_specified: Optional[float] = None
                for v in raw_abs:
                    if v is not None and not (isinstance(v, float) and np.isnan(v)):
                        last_specified = float(v)
                pad_value = last_specified if last_specified is not None else last_value
                raw_abs += [pad_value] * (horizon - len(raw_abs))

            filled: List[float] = []
            current = last_value
            for v in raw_abs:
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    filled.append(current)
                else:
                    current = float(v)
                    filled.append(current)

            future_vals = np.array(filled, dtype=float)

        else:
            log.warning(
                "Unknown ScenarioMode '%s' for %s/%s/%s. Using NONE.",
                scenario_mode,
                model_name,
                ticker,
                reg,
            )
            future_vals = np.full(horizon, last_value, dtype=float)

        future_series[reg] = pd.Series(future_vals, index=future_dates, name=reg)

    if not future_series:
        log.warning("No X_future series built for %s/%s.", model_name, ticker)
        return X_train_df, None

    X_future_df = cast("DataFrame", pd.concat(list(future_series.values()), axis=1))
    X_future_df = cast("DataFrame", X_future_df.loc[:, valid_regs])

    return X_train_df, X_future_df


# ======================================================================
# LSTM with ExoConfig (delegates to canonical torch LSTM)
# ======================================================================


def predict_lstm(
    enriched_data: "DataFrame",
    ticker: str = "Unknown",
    exo_config: Optional[Any] = None,
    progress_callback=None,
) -> Optional["DataFrame"]:
    if pd is None or np is None:
        return None
    if enriched_data is None or "Close" not in enriched_data.columns:
        return None

    # Local import: keeps module import-safe.
    from pandas.tseries.frequencies import to_offset

    try:
        from src.models.lstm import predict_lstm_quantiles  # type: ignore
    except Exception as e:
        log.warning("LSTM: failed to import canonical torch LSTM model: %s", e)
        return None

    close_numeric = pd.to_numeric(enriched_data["Close"], errors="coerce")
    y_series = cast("Series", cast("Series", close_numeric).dropna())

    if y_series.empty:
        log.warning("LSTM: No valid Close data for %s.", ticker)
        return None

    target_index = y_series.index
    future_dates = pd.date_range(
        start=target_index[-1] + to_offset("B"),
        periods=C.FH,
        freq="B",
    )

    X_train_exog: Optional["DataFrame"] = None
    X_future_exog: Optional["DataFrame"] = None
    if exo_config:
        X_train_exog, X_future_exog = build_exog_matrices(
            "LSTM", ticker, enriched_data, target_index, future_dates, exo_config
        )

    # Legacy constants are [q_low, q_mid, q_high]. Canonical API expects (q_low, q_high).
    q_lo = 0.05
    q_hi = 0.95
    try:
        from src.models.intervals import discover_pi_settings  # type: ignore

        pi = discover_pi_settings()
        q_lo = float(pi.q_low)
        q_hi = float(pi.q_high)
    except Exception:
        try:
            qvals = [float(q) for q in list(getattr(C, "LSTM_QUANTILES", []))]
            if len(qvals) >= 2:
                qvals_sorted = sorted(qvals)
                q_lo = float(qvals_sorted[0])
                q_hi = float(qvals_sorted[-1])
        except Exception:
            q_lo, q_hi = 0.05, 0.95

    try:
        res = predict_lstm_quantiles(
            enriched_data,
            ticker=ticker,
            target_col="Close",
            fh=int(C.FH),
            exog_train=X_train_exog,
            exog_future=X_future_exog,
            quantiles=(q_lo, q_hi),
            lookback=int(getattr(C, "LSTM_LOOKBACK", 60)),
            epochs=int(getattr(C, "LSTM_EPOCHS", 60)),
            batch_size=32,
            lstm_units=64,
            dense_units=32,
            dropout=0.10,
            learning_rate=1e-3,
            min_samples=max(120, int(getattr(C, "LSTM_LOOKBACK", 60)) + 25),
            seed=42,
            verbose=0,
        )
    except Exception as e:
        log.warning("LSTM: canonical model failed for %s: %s", ticker, e, exc_info=True)
        return None

    if res is None or res.pred_df is None or res.pred_df.empty:
        return None

    out_df = cast("DataFrame", res.pred_df.copy())

    # Keep legacy shape expectations (exact horizon where possible).
    if len(out_df) >= int(C.FH):
        out_df = cast("DataFrame", out_df.iloc[: int(C.FH)].copy())

    return out_df


# ======================================================================
# DynaMix wrapper (CPU-only worker-backed)
# ======================================================================


def predict_dynamix(
    enriched_data: "DataFrame",
    ticker: str = "Unknown",
    target_col: str = "Close",
    fh: Optional[int] = None,
    standardize: Optional[bool] = None,
    fit_nonstationary: Optional[bool] = None,
    progress_callback=None,
) -> Optional["DataFrame"]:
    if pd is None:
        return None
    if enriched_data is None or target_col not in enriched_data.columns:
        return None

    try:
        from src.models.dynamix import predict_dynamix as _predict_dynamix  # type: ignore
    except Exception as e:
        log.warning("DynaMix: canonical import failed: %s", e)
        return None

    try:
        out = _predict_dynamix(
            enriched_data,
            ticker=ticker,
            target_col=target_col,
            fh=fh,
            standardize=standardize,
            fit_nonstationary=fit_nonstationary,
        )
        if out is None or getattr(out, "empty", True):
            return None
        return cast("DataFrame", out)
    except Exception as e:
        log.warning("DynaMix failed for %s: %s", ticker, e, exc_info=True)
        return None


# ======================================================================
# Random Walk baseline
# ======================================================================


def predict_random_walk(
    enriched_data: "DataFrame",
    progress_callback=None,
) -> Optional["DataFrame"]:
    if pd is None:
        return None
    if enriched_data is None or "Close" not in enriched_data.columns:
        return None

    # Local import: keeps module import-safe.
    from pandas.tseries.frequencies import to_offset

    close_series = cast(
        "Series", pd.to_numeric(enriched_data["Close"], errors="coerce")
    ).dropna()

    if close_series.empty:
        log.warning("Random Walk: 'Close' prices are empty after dropping NaNs.")
        return None

    last_price = float(close_series.iloc[-1])
    drift = float(close_series.diff().mean()) if C.RW_DRIFT_ENABLED else 0.0

    predictions = [last_price + (i + 1) * drift for i in range(C.FH)]
    last_date = close_series.index[-1]
    future_dates = pd.date_range(
        start=last_date + to_offset("B"),
        periods=C.FH,
        freq="B",
    )
    return cast("DataFrame", pd.DataFrame({"RW_Pred": predictions}, index=future_dates))


# ======================================================================
# ARIMAX with ExoConfig (lazy pmdarima, statsmodels fallback)
# ======================================================================


def _predict_arima_statsmodels_fallback(
    enriched_data: "DataFrame",
    ticker: str,
    exo_config: Optional[Any],
) -> Tuple[
    Optional["DataFrame"], Optional[Tuple[int, int, int]], Optional["NDArray[Any]"]
]:
    """
    Fallback ARIMAX path that avoids pmdarima binary wheels.

    Uses canonical statsmodels-backed implementation from src.models.arimax.
    Keeps legacy return shape: (pred_df, model_order, residuals).
    """
    if pd is None or np is None:
        return None, None, None

    try:
        from src.models.arimax import predict_arimax  # type: ignore
    except Exception as e:
        log.warning(
            "ARIMAX fallback unavailable (cannot import src.models.arimax): %s", e
        )
        return None, None, None

    if enriched_data is None or "Close" not in enriched_data.columns:
        return None, None, None

    try:
        # Keep prep logic aligned with primary legacy path.
        arima_data = enriched_data.copy()
        arima_data["Close"] = pd.to_numeric(arima_data["Close"], errors="coerce")
        arima_data = cast("DataFrame", arima_data.asfreq("B").ffill())
        arima_data = cast("DataFrame", arima_data.dropna(subset=["Close"]))
        if arima_data.empty:
            return None, None, None

        y_train = cast("Series", arima_data["Close"])
        target_index = y_train.index

        # Local import keeps module import-safe.
        from pandas.tseries.frequencies import to_offset

        last_dt = pd.Timestamp(cast(Any, target_index[-1]))
        future_dates = pd.date_range(
            start=last_dt + to_offset("B"),
            periods=C.FH,
            freq="B",
        )

        X_train_df: Optional["DataFrame"] = None
        X_future_df: Optional["DataFrame"] = None
        if exo_config is not None:
            X_train_df, X_future_df = build_exog_matrices(
                "ARIMAX", ticker, arima_data, target_index, future_dates, exo_config
            )

        res = predict_arimax(
            arima_data,
            ticker=ticker,
            exo_config=cast(Optional[Dict[str, Any]], exo_config),
            exo_train_df=X_train_df,
            exo_future_df=X_future_df,
        )
        if res is None or res.pred_df is None or res.pred_df.empty:
            return None, None, None

        order_out: Optional[Tuple[int, int, int]] = None
        model_order = getattr(res, "model_order", None)
        if isinstance(model_order, tuple) and len(model_order) == 3:
            try:
                order_out = (
                    int(model_order[0]),
                    int(model_order[1]),
                    int(model_order[2]),
                )
            except Exception:
                order_out = None

        resid_out: Optional["NDArray[Any]"] = None
        residuals = getattr(res, "residuals", None)
        if residuals is not None:
            try:
                arr = cast("NDArray[Any]", np.asarray(residuals, dtype=float))
                resid_out = arr if arr.size > 0 else None
            except Exception:
                resid_out = None

        return cast("DataFrame", res.pred_df.copy()), order_out, resid_out

    except Exception as e:
        log.warning(
            "ARIMAX statsmodels fallback failed for %s: %s", ticker, e, exc_info=True
        )
        return None, None, None


def predict_arima(
    enriched_data: "DataFrame",
    ticker: str,
    exo_config: Optional[Any] = None,
    progress_callback=None,
) -> Tuple[
    Optional["DataFrame"], Optional[Tuple[int, int, int]], Optional["NDArray[Any]"]
]:
    if pd is None or np is None:
        return None, None, None

    # Local import: keeps module import-safe.
    from pandas.tseries.frequencies import to_offset

    try:
        if enriched_data is None or "Close" not in enriched_data.columns:
            log.warning("ARIMAX: Missing 'Close' column in enriched_data.")
            return None, None, None

        import pmdarima as pm  # type: ignore

        arima_data = enriched_data.copy()
        arima_close = pd.to_numeric(arima_data["Close"], errors="coerce")
        arima_data["Close"] = arima_close
        arima_data = cast("DataFrame", arima_data.asfreq("B").ffill())
        arima_data = arima_data.dropna(subset=["Close"])

        if arima_data.empty or len(arima_data) < (
            C.ARIMA_MAX_P + C.ARIMA_MAX_Q + C.ARIMA_MAX_D + 1
        ):
            log.warning(
                "ARIMAX: Insufficient data (%d rows) after cleaning.", len(arima_data)
            )
            return None, None, None

        y_train = cast("Series", arima_data["Close"])
        target_index = y_train.index
        future_dates = pd.date_range(
            start=target_index[-1] + to_offset("B"),
            periods=C.FH,
            freq="B",
        )

        X_train_df: Optional["DataFrame"] = None
        X_future_df: Optional["DataFrame"] = None

        if exo_config is not None:
            X_train_df, X_future_df = build_exog_matrices(
                "ARIMAX", ticker, arima_data, target_index, future_dates, exo_config
            )

        X_train_arr: Optional["NDArray[Any]"] = None
        X_future_arr: Optional["NDArray[Any]"] = None

        if X_train_df is not None and not X_train_df.empty:
            X_train_arr = cast("NDArray[Any]", np.asarray(X_train_df, dtype=float))

        if X_future_df is not None and not X_future_df.empty:
            arr = cast("NDArray[Any]", np.asarray(X_future_df, dtype=float))
            if arr.ndim == 1:
                arr = cast("NDArray[Any]", arr.reshape(-1, 1))
            X_future_arr = arr

        if X_train_arr is not None:
            auto_model = pm.auto_arima(
                y=y_train,
                X=X_train_arr,
                start_p=1,
                start_q=1,
                max_p=C.ARIMA_MAX_P,
                max_q=C.ARIMA_MAX_Q,
                max_d=C.ARIMA_MAX_D,
                seasonal=C.ARIMA_SEASONAL,
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
            )
        else:
            auto_model = pm.auto_arima(
                y=y_train,
                X=None,
                start_p=1,
                start_q=1,
                max_p=C.ARIMA_MAX_P,
                max_q=C.ARIMA_MAX_Q,
                max_d=C.ARIMA_MAX_D,
                seasonal=C.ARIMA_SEASONAL,
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
            )

        if auto_model is None:
            log.warning("ARIMAX: auto_arima failed to find a suitable model.")
            return None, None, None

        alpha_i = 0.10
        try:
            from src.models.intervals import discover_pi_settings  # type: ignore

            alpha_i = float(discover_pi_settings().alpha)
        except Exception:
            alpha_i = 0.10

        if X_future_arr is not None:
            predictions, conf_int = auto_model.predict(
                n_periods=C.FH,
                X=X_future_arr,
                return_conf_int=True,
                alpha=alpha_i,
            )
        else:
            predictions, conf_int = auto_model.predict(
                n_periods=C.FH,
                X=None,
                return_conf_int=True,
                alpha=alpha_i,
            )

        model_order = auto_model.order
        residuals = cast("NDArray[Any]", auto_model.resid())

        qhat = 0.0
        try:
            from src.models.intervals import (  # type: ignore
                discover_pi_settings,
                residual_quantile_expansion,
            )

            pi = discover_pi_settings()
            if bool(pi.calibration_enabled):
                qhat = residual_quantile_expansion(
                    residuals,
                    alpha=float(pi.alpha),
                    min_samples=int(pi.calibration_min_samples),
                )
        except Exception:
            qhat = 0.0

        if qhat > 0.0 and np.isfinite(qhat):
            conf_int[:, 0] = conf_int[:, 0] - float(qhat)
            conf_int[:, 1] = conf_int[:, 1] + float(qhat)

        result_df = pd.DataFrame(
            {
                "ARIMAX_Pred": predictions,
                "ARIMAX_Lower": conf_int[:, 0],
                "ARIMAX_Upper": conf_int[:, 1],
            },
            index=future_dates,
        )
        return cast("DataFrame", result_df), model_order, residuals

    except Exception as e:
        log.warning(
            "ARIMAX pmdarima path failed for %s: %s. Trying statsmodels fallback.",
            ticker,
            e,
        )
        return _predict_arima_statsmodels_fallback(enriched_data, ticker, exo_config)


# ======================================================================
# GARCH / ARX-GARCH with ExoConfig (arch gated via src.utils.compat)
# ======================================================================


def predict_arch_model(
    enriched_data: "DataFrame",
    ticker: str,
    exo_config: Optional[Any] = None,
    progress_callback=None,
):
    if not opt.HAS_ARCH:
        return None, None, None
    if pd is None or np is None:
        return None, None, None
    if enriched_data is None or "Close" not in enriched_data.columns:
        return None, None, None

    # Local import: keeps module import-safe.
    from pandas.tseries.frequencies import to_offset

    try:
        log.info("Starting ARX-GARCH model fitting and forecasting...")

        close_num = pd.to_numeric(enriched_data["Close"], errors="coerce")
        returns = 100.0 * cast("Series", close_num).pct_change().dropna()

        if returns.empty:
            log.warning("GARCH: Returns series is empty after pct_change/dropna.")
            return None, None, None

        target_index = returns.index
        future_dates = pd.date_range(
            start=enriched_data.index[-1] + to_offset("B"),
            periods=C.FH,
            freq="B",
        )

        X_train_df: Optional["DataFrame"] = None
        X_future_df: Optional["DataFrame"] = None
        x_train_arr: Optional["NDArray[Any]"] = None
        x_future_arr: Optional["NDArray[Any]"] = None

        if exo_config is not None:
            X_train_df, X_future_df = build_exog_matrices(
                "GARCH", ticker, enriched_data, target_index, future_dates, exo_config
            )

        if X_train_df is not None and not X_train_df.empty:
            X_train_aligned = cast(
                "DataFrame", X_train_df.reindex(index=returns.index).dropna(how="any")
            )
            if not X_train_aligned.empty:
                common_index = X_train_aligned.index
                returns_aligned = returns.reindex(common_index).dropna()
                X_train_aligned = cast(
                    "DataFrame", X_train_aligned.reindex(index=returns_aligned.index)
                )

                if returns_aligned.empty or X_train_aligned.empty:
                    log.warning(
                        "GARCH: After aligning returns and exogenous regressors, series became empty. "
                        "Falling back to GARCH without exog."
                    )
                    X_train_df = None
                else:
                    returns = returns_aligned
                    x_train_arr = cast(
                        "NDArray[Any]", np.asarray(X_train_aligned, dtype=float)
                    )
            else:
                log.warning(
                    "GARCH: X_train became empty after aligning with returns. "
                    "Falling back to GARCH without exogenous regressors."
                )
                X_train_df = None

        arch_model_fn = opt.arch_model  # type: ignore

        if x_train_arr is not None:
            am = arch_model_fn(
                returns,
                x=x_train_arr,
                mean="ARX",
                lags=1,
                vol="GARCH",
                p=1,
                q=1,
                dist="normal",
            )
        else:
            am = arch_model_fn(
                returns,
                mean="AR",
                lags=1,
                vol="GARCH",
                p=1,
                q=1,
                dist="normal",
            )

        res = am.fit(update_freq=5, disp="off")

        if (
            X_future_df is not None
            and not X_future_df.empty
            and x_train_arr is not None
        ):
            num_steps, num_regs = X_future_df.shape
            if num_steps != C.FH:
                x_future_arr = None
            else:
                if num_regs == 1:
                    vals = X_future_df.iloc[:, 0].to_numpy(dtype=float)
                    x_future_arr = cast("NDArray[Any]", vals.reshape(1, -1))
                else:
                    series_list: List["NDArray[Any]"] = []
                    for col in X_future_df.columns:
                        col_vals = X_future_df[col].to_numpy(dtype=float).reshape(1, -1)
                        series_list.append(cast("NDArray[Any]", col_vals))
                    x_future_arr = cast("NDArray[Any]", np.stack(series_list, axis=0))

        if x_future_arr is not None:
            forecasts = res.forecast(horizon=C.FH, x=x_future_arr, reindex=False)
        else:
            forecasts = res.forecast(horizon=C.FH, reindex=False)

        mean_forecast = forecasts.mean.iloc[0].values
        variance_forecast = forecasts.variance.iloc[0].values

        last_price = float(enriched_data["Close"].iloc[-1])
        price_forecast: List[float] = [
            last_price * (1.0 + float(mean_forecast[0]) / 100.0)
        ]
        for i in range(1, C.FH):
            price_forecast.append(
                price_forecast[i - 1] * (1.0 + float(mean_forecast[i]) / 100.0)
            )

        price_forecast_df = pd.DataFrame(
            {"GARCH_Pred": price_forecast}, index=future_dates
        )
        volatility_forecast_df = pd.DataFrame(
            {"Volatility_Forecast": variance_forecast}, index=future_dates
        )

        return (
            cast("DataFrame", price_forecast_df),
            cast("DataFrame", volatility_forecast_df),
            res,
        )

    except Exception as e:
        log.error("Error during GARCH model fitting: %s", e, exc_info=True)
        return None, None, None


# ======================================================================
# VAR model (lazy statsmodels)
# ======================================================================


def predict_var(
    enriched_data: "DataFrame",
    progress_callback=None,
) -> Optional["DataFrame"]:
    if not opt.HAS_STATSMODELS:
        return None
    if pd is None:
        return None

    # Local import: keeps module import-safe.
    from pandas.tseries.frequencies import to_offset

    var_cols = ["Close", "ATR (14)"]
    if "Volume" in enriched_data.columns and enriched_data["Volume"].nunique() > 1:
        var_cols.append("Volume")

    for col in var_cols:
        if col not in enriched_data.columns:
            log.warning("VAR model requires column '%s', but it is missing.", col)
            return None
        enriched_data[col] = pd.to_numeric(enriched_data[col], errors="coerce")

    try:
        from statsmodels.tsa.api import VAR  # type: ignore

        var_data = enriched_data[var_cols]
        var_data = var_data.dropna(how="any").asfreq("B").ffill().dropna(how="any")

        if var_data.empty or len(var_data) < C.VAR_MAX_LAGS + 5:
            log.warning(
                "VAR: Insufficient data (%d rows) after cleaning.", len(var_data)
            )
            return None

        differenced = var_data.diff().dropna()
        if differenced.empty:
            return None

        model = VAR(differenced)
        selected_order = model.select_order(maxlags=C.VAR_MAX_LAGS)
        best_lag = selected_order.aic

        if best_lag == 0:
            return None

        results = model.fit(best_lag)
        lag_order = results.k_ar

        if len(differenced) < lag_order:
            return None

        forecasted_diffs = results.forecast(
            y=differenced.values[-lag_order:], steps=C.FH
        )

        last_values = var_data.iloc[-1]
        future_dates = pd.date_range(
            start=var_data.index[-1] + to_offset("B"),
            periods=C.FH,
            freq="B",
        )
        df_forecast = pd.DataFrame(
            forecasted_diffs, index=future_dates, columns=var_data.columns
        )
        df_forecast = last_values.add(df_forecast.cumsum())
        return cast("DataFrame", pd.DataFrame({"VAR_Pred": df_forecast["Close"]}))

    except Exception as e:
        log.error("Error during VAR model fitting: %s", e, exc_info=True)
        return None


# ======================================================================
# ETS model (lazy statsmodels HoltWinters)
# ======================================================================


def predict_exp_smoothing(
    enriched_data: "DataFrame",
    progress_callback=None,
) -> Optional["DataFrame"]:
    if pd is None:
        return None
    if enriched_data is None or "Close" not in enriched_data.columns:
        return None

    # Local import: keeps module import-safe.
    from pandas.tseries.frequencies import to_offset  # noqa: F401

    ets_series = cast(
        "Series", pd.to_numeric(enriched_data["Close"], errors="coerce")
    ).dropna()
    ets_series = ets_series.asfreq("B").ffill().dropna()

    if ets_series.empty:
        return None

    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore

        model = ExponentialSmoothing(
            ets_series,
            trend=C.ETS_TREND,
            seasonal=C.ETS_SEASONAL,
            seasonal_periods=C.ETS_SEASONAL_PERIODS,
        ).fit()
        predictions = model.forecast(steps=C.FH)
        return cast("DataFrame", pd.DataFrame({"ETS_Pred": predictions}))

    except Exception as e:
        log.error("ETS: error fitting/forecasting: %s", e, exc_info=True)
        return None


# ======================================================================
# PCE wrapper with ExoConfig
# ======================================================================


def predict_pce_narx(
    enriched_data: "DataFrame",
    ticker: str = "Unknown",
    exo_config: Optional[Any] = None,
    progress_callback=None,
) -> Optional["DataFrame"]:
    if pd is None:
        return None
    if enriched_data is None or "Close" not in enriched_data.columns:
        return None

    # Local import: keeps module import-safe.
    from pandas.tseries.frequencies import to_offset

    y_series = cast(
        "Series", pd.to_numeric(enriched_data["Close"], errors="coerce")
    ).dropna()
    if y_series.empty:
        return None

    target_index = y_series.index
    future_dates = pd.date_range(
        start=target_index[-1] + to_offset("B"),
        periods=C.FH,
        freq="B",
    )

    X_train_exog: Optional["DataFrame"] = None
    X_future_exog: Optional["DataFrame"] = None

    if exo_config:
        X_train_exog, X_future_exog = build_exog_matrices(
            "PCE", ticker, enriched_data, target_index, future_dates, exo_config
        )

    # Canonical-first: prefer in-process src implementation (best effort).
    try:
        from src.models.pce_narx import predict_pce_narx as _predict  # type: ignore

        out = _predict(
            enriched_data=enriched_data,
            ticker=ticker,
            fh=int(getattr(C, "FH", 3)),
            exog_train_df=X_train_exog,
            exog_future_df=X_future_exog,
            progress_callback=progress_callback,
        )
        if out is not None and not getattr(out, "empty", True):
            return cast("DataFrame", out)
    except Exception as e_src:
        log.info(
            "src.models.pce_narx unavailable (%s). Trying compat.PCEModel...", e_src
        )

    # Legacy compat shim (same-env). In FIN-core, this is expected to be unavailable due to NumPy<2.
    try:
        from compat import PCEModel  # type: ignore

        out2 = PCEModel.predict_pce_narx(
            enriched_data,
            exog_train_df=X_train_exog,
            exog_future_df=X_future_exog,
            progress_callback=progress_callback,
        )
        if out2 is not None and not getattr(out2, "empty", True):
            return cast("DataFrame", out2)
    except Exception as e:
        log.info(
            "compat.PCEModel path failed (%s). Falling back to external PCE worker.", e
        )

    # External worker fallback (required runtime capability under NumPy-2 venv)
    try:
        out3 = _run_pce_worker(
            enriched_data=enriched_data,
            exog_train_df=X_train_exog,
            exog_future_df=X_future_exog,
            ticker=ticker,
        )
        if out3 is None or getattr(out3, "empty", True):
            return None
        return cast("DataFrame", out3)
    except Exception as e:
        log.warning("PCE worker fallback failed: %s", e, exc_info=True)
        return None


__all__ = [
    "run_external_script",
    "run_external_ti_calculator",
    "run_external_torch_forecasting",
    "build_exog_matrices",
    "predict_dynamix",
    "predict_lstm",
    "predict_random_walk",
    "predict_arima",
    "predict_arch_model",
    "predict_var",
    "predict_exp_smoothing",
    "predict_pce_narx",
]
