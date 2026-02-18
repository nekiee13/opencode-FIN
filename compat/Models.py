# ------------------------
# compat/Models.py
# ------------------------
"""
FIN Legacy Models facade (compat layer) — delegation-only.

Phase-1 invariants:
- compat/ must not contain algorithmic implementations.
- src/ is the canonical implementation source of truth.

This module preserves the legacy public API exactly by delegating to:
  src.models.compat_api
"""

from __future__ import annotations

# from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

# Delegate all legacy-API functions to canonical src implementation.
from src.models.compat_api import (  # noqa: F401
    build_exog_matrices,
    predict_arch_model,
    predict_arima,
    predict_exp_smoothing,
    predict_lstm,
    predict_pce_narx,
    predict_random_walk,
    predict_var,
    run_external_torch_forecasting,
    run_external_script,
    run_external_ti_calculator,
)

__all__ = [
    "run_external_script",
    "run_external_ti_calculator",
    "run_external_torch_forecasting",
    "build_exog_matrices",
    "predict_lstm",
    "predict_random_walk",
    "predict_arima",
    "predict_arch_model",
    "predict_var",
    "predict_exp_smoothing",
    "predict_pce_narx",
]
