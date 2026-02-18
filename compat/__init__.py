# ------------------------
# compat/__init__.py
# ------------------------
"""
compat package (legacy bridge).

Phase-1 Path Stabilization:
- compat/ must be thin: no heavy imports, no modeling logic.
- src/ is canonical.

This package-level __init__ provides backward-compatible aliases for:
- capability flags historically accessed as `compat.HAS_*`
- safe imported symbols historically accessed as `compat.torch`, `compat.tf`, `compat.arch_model`, etc.

Canonical source:
  src.utils.compat
"""

from __future__ import annotations

from typing import Any, Dict

# ----------------------------------------------------------------------
# Static symbol declarations (Pylance-friendly)
# ----------------------------------------------------------------------
# These names must exist at module import time so __all__ can be validated.
# Runtime values are overwritten below from src.utils.compat when available.

HAS_NUMPY: bool = False
HAS_PANDAS: bool = False

HAS_STATSMODELS: bool = False
HAS_ARCH: bool = False
HAS_TORCH: bool = False
HAS_TENSORFLOW: bool = False
HAS_RUPTURES: bool = False

HAS_SVL: bool = False
HAS_SVL_HURST: bool = False
HAS_YFINANCE: bool = False
HAS_RIPSER: bool = False
HAS_TDA: bool = False

CAPABILITIES: Dict[str, Any] = {}

np: Any = None
pd: Any = None
torch: Any = None
tf: Any = None
arch_model: Any = None

# ----------------------------------------------------------------------
# Defaults and import bridge
# ----------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "HAS_NUMPY": HAS_NUMPY,
    "HAS_PANDAS": HAS_PANDAS,
    "HAS_STATSMODELS": HAS_STATSMODELS,
    "HAS_ARCH": HAS_ARCH,
    "HAS_TORCH": HAS_TORCH,
    "HAS_TENSORFLOW": HAS_TENSORFLOW,
    "HAS_RUPTURES": HAS_RUPTURES,
    "HAS_SVL": HAS_SVL,
    "HAS_SVL_HURST": HAS_SVL_HURST,
    "HAS_YFINANCE": HAS_YFINANCE,
    "HAS_RIPSER": HAS_RIPSER,
    "HAS_TDA": HAS_TDA,
    "CAPABILITIES": CAPABILITIES,
    "np": np,
    "pd": pd,
    "torch": torch,
    "tf": tf,
    "arch_model": arch_model,
}

_NAMES = (
    "HAS_NUMPY",
    "HAS_PANDAS",
    "HAS_STATSMODELS",
    "HAS_ARCH",
    "HAS_TORCH",
    "HAS_TENSORFLOW",
    "HAS_RUPTURES",
    "HAS_SVL",
    "HAS_SVL_HURST",
    "HAS_YFINANCE",
    "HAS_RIPSER",
    "HAS_TDA",
    "CAPABILITIES",
    "np",
    "pd",
    "torch",
    "tf",
    "arch_model",
)

try:  # pragma: no cover
    from src.utils import compat as _cap  # type: ignore
except Exception:  # pragma: no cover
    _cap = None  # type: ignore

for _name in _NAMES:
    if _cap is None:
        _value = _DEFAULTS[_name]
    else:
        _value = getattr(_cap, _name, _DEFAULTS[_name])

    # Normalize CAPABILITIES to a plain dict for stable introspection.
    if _name == "CAPABILITIES":
        try:
            _value = dict(_value or {})
        except Exception:
            _value = {}

    globals()[_name] = _value

# Pylance-friendly: keep __all__ literal and consistent with declared names.
__all__ = [
    "HAS_NUMPY",
    "HAS_PANDAS",
    "HAS_STATSMODELS",
    "HAS_ARCH",
    "HAS_TORCH",
    "HAS_TENSORFLOW",
    "HAS_RUPTURES",
    "HAS_SVL",
    "HAS_SVL_HURST",
    "HAS_YFINANCE",
    "HAS_RIPSER",
    "HAS_TDA",
    "CAPABILITIES",
    "np",
    "pd",
    "torch",
    "tf",
    "arch_model",
]
