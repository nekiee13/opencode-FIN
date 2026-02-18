# ------------------------
# compat\ExoConfig.py
# ------------------------
"""
FIN legacy ExoConfig facade (compat layer).

Location
--------
compat/ExoConfig.py

Purpose
-------
Preserve legacy import paths (e.g., `import ExoConfig`) while the canonical
implementation lives under `src.exo.exo_config`.

This module re-exports:
- ExoConfigType
- ExoSpec
- load_exo_config
- get_exog_config
- get_enabled_regressors
- get_exog_spec

Notes
-----
- Side-effect free on import (no file I/O, no mkdir).
- New code should prefer `src.exo.exo_config` directly, and use
  `src.config.paths.EXO_CONFIG_PATH` as the canonical CSV location.
"""

from __future__ import annotations

from src.exo.exo_config import (  # noqa: F401
    ExoConfigType,
    ExoSpec,
    get_enabled_regressors,
    get_exog_config,
    get_exog_spec,
    load_exo_config,
)

__all__ = [
    "ExoConfigType",
    "ExoSpec",
    "load_exo_config",
    "get_exog_config",
    "get_enabled_regressors",
    "get_exog_spec",
]
