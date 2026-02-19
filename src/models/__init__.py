# ------------------------
# src/models/__init__.py
# ------------------------
"""
src.models package

Phase-1 Path Stabilization rules
--------------------------------
- No eager importing of model implementations at package import time.
- Import models explicitly where they are used (facade or callers).

Pylance compatibility
---------------------
Pylance validates that every name listed in __all__ exists in the module namespace.
To avoid eager imports at runtime while satisfying static analysis, submodules are
imported only under TYPE_CHECKING, and are lazily loaded at runtime via __getattr__.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, List

# Static-only imports for Pylance/type-checkers (no runtime cost).
# These declarations make names "present in module" for __all__ validation.
if TYPE_CHECKING:  # pragma: no cover
    from . import arimax as arimax
    from . import compat_api as compat_api
    from . import dynamix as dynamix
    from . import ets as ets
    from . import facade as facade
    from . import garch as garch
    from . import lstm as lstm
    from . import pce_narx as pce_narx
    from . import random_walk as random_walk
    from . import var as var

__all__ = [
    "facade",
    "compat_api",
    "dynamix",
    "arimax",
    "ets",
    "garch",
    "lstm",
    "pce_narx",
    "random_walk",
    "var",
]

_SUBMODULES: List[str] = list(__all__)


def __getattr__(name: str):
    """
    Lazy-load submodules on first attribute access.

    Example:
        import src.models as m
        m.var.predict_var(...)
    """
    if name in _SUBMODULES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> List[str]:
    """Expose lazy submodules in dir(src.models)."""
    return sorted(list(globals().keys()) + _SUBMODULES)
