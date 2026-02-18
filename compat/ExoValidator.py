# ------------------------
# compat\ExoValidator.py
# ------------------------
"""
FIN legacy ExoValidator facade (compat layer).

Location
--------
compat/ExoValidator.py

Purpose
-------
Preserve legacy import paths (e.g., `import ExoValidator`) while the canonical
implementation lives under `src.exo.exo_validator`.

This module re-exports:
- ValidationParams
- validate_abs_scenario_path
- validate_exo_config_for_run

Design
------
- Side-effect free on import (no file I/O, no mkdir).
- Compatibility-only: new/refactored code should import from `src.exo.exo_validator`.
"""

from __future__ import annotations

from src.exo.exo_validator import (  # noqa: F401
    ValidationParams,
    validate_abs_scenario_path,
    validate_exo_config_for_run,
)

__all__ = [
    "ValidationParams",
    "validate_abs_scenario_path",
    "validate_exo_config_for_run",
]
