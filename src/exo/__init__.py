# ------------------------
# exo\__init__.py
# ------------------------
"""
FIN exogenous modeling package.

Purpose
-------
Provides exogenous-regressor configuration loading, validation, and scenario
handling for FIN forecasting models.

Design
------
- Side-effect free on import.
- Canonical implementations live in submodules:
    - exo_config
    - exo_validator
"""

from __future__ import annotations

from .exo_config import ExoConfigType, ExoSpec, load_exo_config, get_exog_config, get_enabled_regressors, get_exog_spec
from .exo_validator import ValidationParams, validate_abs_scenario_path, validate_exo_config_for_run

__all__ = [
    "ExoConfigType",
    "ExoSpec",
    "load_exo_config",
    "get_exog_config",
    "get_enabled_regressors",
    "get_exog_spec",
    "ValidationParams",
    "validate_abs_scenario_path",
    "validate_exo_config_for_run",
]
