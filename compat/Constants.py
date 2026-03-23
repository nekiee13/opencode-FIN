# ------------------------
# compat\Constants.py
# ------------------------
"""
Backward-compatibility Constants bridge for FIN (Refactor Phase 1).

This module preserves the legacy Constants.py interface (names used across the
existing codebase) while sourcing *paths* from the new path stabilization layer:

    src.config.paths

Key invariants:
- Import-time side effects are avoided (no directory creation on import).
- No hardcoded absolute paths.
- Legacy scripts can continue to `import Constants as C` during migration.

Notes
-----
- APP_ROOT_DIR in the legacy project was set at runtime by app3G.py. In FIN, we
  treat APP_ROOT_DIR as a derived value from src.config.paths.APP_ROOT.
- If an entrypoint needs directories to exist, it must call
  `src.config.paths.ensure_directories()` explicitly.
"""

from __future__ import annotations

from pathlib import Path

# --- Application Metadata ---
APP_VERSION = "2.1-refactor-phase-1"

# --- Dynamic Paths (sourced from src.config.paths) ---
try:
    from src.config import paths as _paths
except Exception as e:  # pragma: no cover
    # Fail fast with a clear message; Constants is widely imported.
    raise RuntimeError(
        "Failed to import src.config.paths. "
        "Ensure FIN is executed with project root on sys.path (recommended: run from FIN root), "
        "or that the package layer is discoverable. Under migration, this is a hard requirement. "
        f"Original error: {e}"
    ) from e


# Legacy name preserved; now derived from stabilization layer.
APP_ROOT_DIR: str = str(_paths.APP_ROOT)

# Legacy folder constants preserved; now FIN-relative.
# In TS these were hardcoded to F:\\xPy\\TS\\DATA and F:\\xPy\\TS\\Graphs.
DATA_FOLDER: str = str(_paths.DATA_TICKERS_DIR)
GRAPHS_FOLDER: str = str(_paths.GRAPHS_DIR)

# Optional/commonly used additional folders (non-breaking additions).
OUTPUT_FOLDER: str = str(_paths.OUTPUT_DIR)
LOGS_FOLDER: str = str(_paths.LOGS_DIR)
CONFIG_FOLDER: str = str(_paths.CONFIG_DIR)
EXO_REGRESSORS_CSV: str = str(_paths.EXO_CONFIG_PATH)

# ----------------------------------------------------------------------
# PCE-NARX external worker (NumPy 2.x isolated interpreter)
# ----------------------------------------------------------------------
#
# Purpose:
# - FIN-core runtime may run under NumPy<2.
# - PCE-NARX stack (chaospy/numpoly) may require NumPy>=2.
# - External worker execution isolates PCE into a separate interpreter.
#
# Resolution order (implemented in src/models/compat_api.py):
# 1) FIN_PCE_PY_EXE environment variable
# 2) This constant (PCE_WORKER_PY_EXE) if set and exists
# 3) Known default candidates (e.g., F:\vEnv\FIN_PCE\python.exe)
#
# Recommended value example (machine-specific):
#   r"F:\vEnv\FIN_PCE\python.exe"
#
# Default is empty to avoid embedding machine-specific paths in repo defaults.
PCE_WORKER_PY_EXE: str = ""


# ----------------------------------------------------------------------
# DynaMix worker/model integration (CPU-only by default)
# ----------------------------------------------------------------------
#
# DynaMix can run either in the current interpreter or an explicit external
# interpreter (for dependency isolation).
#
# Resolution order for worker python (implemented in src/models/dynamix.py):
# 1) FIN_DYNAMIX_PY_EXE env var
# 2) DYNAMIX_WORKER_PY_EXE (this constant) when path exists
# 3) sys.executable
#
# DynaMix repository path resolution:
# 1) FIN_DYNAMIX_REPO env var
# 2) DYNAMIX_REPO_PATH (this constant)
# 3) <APP_ROOT>/vendor/DynaMix-python

DYNAMIX_ENABLED = True
DYNAMIX_FORCE_CPU = True
DYNAMIX_REPO_PATH = str((_paths.APP_ROOT / "vendor" / "DynaMix-python").resolve())
DYNAMIX_WORKER_PY_EXE: str = ""

DYNAMIX_MIN_DATA_LENGTH = 30
DYNAMIX_CONTEXT_STEPS = 2048
DYNAMIX_STANDARDIZE = True
DYNAMIX_FIT_NONSTATIONARY = False
DYNAMIX_PREPROCESSING_METHOD = "pos_embedding"
DYNAMIX_TIMEOUT_SEC = 300


# --- Ticker and Indicator Lists ---
TICKERS = ["TNX", "AAPL", "QQQ", "VIX", "GSPC", "DJI"]
INDICATORS_0_100 = [
    "RSI (14)",
    "Stochastic %K",
    "STOCH_%D",
    "Williams %R",
    "Ultimate Oscillator",
]


# --- General Forecasting Parameters ---
FH = 3  # Forecast Horizon in business days


# --- Follow-up ML VBG Parameters ---
VBG_DB_FILE: str = str(_paths.OUT_I_CALC_ML_VG_DB_PATH.resolve())
VBG_MEMORY_TAIL = 4
VBG_BOOTSTRAP_ENABLED = True
VBG_BOOTSTRAP_SCORE = 99.0


# --- Predictive Interval Harmonization (cross-model) ---
# Target: calibrated central 86% predictive intervals.
PI_COVERAGE = 0.86
PI_ALPHA = 0.14
PI_Q_LOW = 0.07
PI_Q_HIGH = 0.93

# Lightweight residual-quantile post-hoc calibration toggle.
PI_CALIBRATION_ENABLED = True
PI_CALIBRATION_MIN_SAMPLES = 30

# Model-specific PI narrowing multipliers (1.0 = unchanged).
# Applied only to final interval half-width in each model.
PCE_PI_WIDTH_MULT = 0.22
LSTM_PI_WIDTH_MULT = 0.30


# --- VAR Model Parameters ---
VAR_MAX_LAGS = 15  # Max lags to check for the VAR model


# --- LSTM Model Parameters ---
LSTM_LOOKBACK = 28
LSTM_EPOCHS = 240
LSTM_TRAIN_WINDOW = 500
LSTM_QUANTILES = [0.05, 0.5, 0.95]


# --- Random Walk Model Parameters ---
RW_DRIFT_ENABLED = True


# --- ARIMA Model Parameters ---
ARIMA_MAX_P = 5
ARIMA_MAX_Q = 5
ARIMA_MAX_D = 2
ARIMA_SEASONAL = False


# --- ETS Model Parameters ---
ETS_TREND = "add"
ETS_SEASONAL = None
ETS_SEASONAL_PERIODS = None


# --- Regime & Extrema Overlay Parameters ---
SHOW_PEAKS_TROUGHS = True
SHOW_REGIMES = True
REGIME_METHOD = "rbf"
PELT_PENALTY = 1

# Legacy tuning retained
PEAK_PROM = 0.08
PEAK_DIST = 5
PEAK_WIDTH = 2


# --- Compatibility: provide Path objects where useful (non-breaking additions) ---
# Some refactored modules may prefer Path types; legacy code can ignore these.
APP_ROOT_PATH: Path = _paths.APP_ROOT
DATA_PATH: Path = _paths.DATA_TICKERS_DIR
GRAPHS_PATH: Path = _paths.GRAPHS_DIR
OUTPUT_PATH: Path = _paths.OUTPUT_DIR
LOGS_PATH: Path = _paths.LOGS_DIR
CONFIG_PATH: Path = _paths.CONFIG_DIR
EXO_CONFIG_PATH: Path = _paths.EXO_CONFIG_PATH


__all__ = [
    # Metadata
    "APP_VERSION",
    # Legacy path names
    "APP_ROOT_DIR",
    "DATA_FOLDER",
    "GRAPHS_FOLDER",
    # Additional folders
    "OUTPUT_FOLDER",
    "LOGS_FOLDER",
    "CONFIG_FOLDER",
    "EXO_REGRESSORS_CSV",
    # PCE worker
    "PCE_WORKER_PY_EXE",
    # DynaMix integration
    "DYNAMIX_ENABLED",
    "DYNAMIX_FORCE_CPU",
    "DYNAMIX_REPO_PATH",
    "DYNAMIX_WORKER_PY_EXE",
    "DYNAMIX_MIN_DATA_LENGTH",
    "DYNAMIX_CONTEXT_STEPS",
    "DYNAMIX_STANDARDIZE",
    "DYNAMIX_FIT_NONSTATIONARY",
    "DYNAMIX_PREPROCESSING_METHOD",
    "DYNAMIX_TIMEOUT_SEC",
    # Lists
    "TICKERS",
    "INDICATORS_0_100",
    # Parameters
    "FH",
    "VBG_DB_FILE",
    "VBG_MEMORY_TAIL",
    "VBG_BOOTSTRAP_ENABLED",
    "VBG_BOOTSTRAP_SCORE",
    "PI_COVERAGE",
    "PI_ALPHA",
    "PI_Q_LOW",
    "PI_Q_HIGH",
    "PI_CALIBRATION_ENABLED",
    "PI_CALIBRATION_MIN_SAMPLES",
    "PCE_PI_WIDTH_MULT",
    "LSTM_PI_WIDTH_MULT",
    "VAR_MAX_LAGS",
    "LSTM_LOOKBACK",
    "LSTM_EPOCHS",
    "LSTM_TRAIN_WINDOW",
    "LSTM_QUANTILES",
    "RW_DRIFT_ENABLED",
    "ARIMA_MAX_P",
    "ARIMA_MAX_Q",
    "ARIMA_MAX_D",
    "ARIMA_SEASONAL",
    "ETS_TREND",
    "ETS_SEASONAL",
    "ETS_SEASONAL_PERIODS",
    "SHOW_PEAKS_TROUGHS",
    "SHOW_REGIMES",
    "REGIME_METHOD",
    "PELT_PENALTY",
    "PEAK_PROM",
    "PEAK_DIST",
    "PEAK_WIDTH",
    # Path objects
    "APP_ROOT_PATH",
    "DATA_PATH",
    "GRAPHS_PATH",
    "OUTPUT_PATH",
    "LOGS_PATH",
    "CONFIG_PATH",
    "EXO_CONFIG_PATH",
]
