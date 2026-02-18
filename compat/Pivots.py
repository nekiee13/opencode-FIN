# ------------------------
# compat/Pivots.py
# ------------------------
"""
Legacy Pivots (compat layer) — delegation-only.

Phase-1:
- Canonical implementation lives in src.utils.pivots
- compat keeps module name stable for legacy scripts
"""

from __future__ import annotations

from typing import Any

# Best-effort re-exports for legacy symbol surface
try:  # pragma: no cover
    from src.utils import pivots as _canon  # type: ignore

    _EXPORTS = (
        "calculate_latest_pivot_points",
        "format_pivot_table",
        "PivotLevels",
        "PivotConfig",
    )
    for _name in _EXPORTS:
        if hasattr(_canon, _name):
            globals()[_name] = getattr(_canon, _name)
except Exception:  # pragma: no cover
    pass


def calculate_latest_pivot_points(*args: Any, **kwargs: Any):
    from src.utils.pivots import calculate_latest_pivot_points as _impl  # type: ignore
    return _impl(*args, **kwargs)


def format_pivot_table(*args: Any, **kwargs: Any):
    from src.utils.pivots import format_pivot_table as _impl  # type: ignore
    return _impl(*args, **kwargs)


__all__ = ["calculate_latest_pivot_points", "format_pivot_table"]
