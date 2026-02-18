# ------------------------
# compat/TDAIndicators.py
# ------------------------
"""
Legacy TDAIndicators (compat layer) — delegation-only.

Phase-1:
- Canonical implementation lives in src.structural.tda_indicators
- compat delegates while preserving public API surface
"""

from __future__ import annotations

from typing import Any

# Best-effort re-exports for legacy symbol surface
try:  # pragma: no cover
    from src.structural import tda_indicators as _canon  # type: ignore

    _EXPORTS = (
        "compute_tda_for_ticker",
        "compute_tda_context",
        "build_tda_context_markdown",
        "build_tda_metrics_df",
        "TDAParams",
        "TDAResult",
    )
    for _name in _EXPORTS:
        if hasattr(_canon, _name):
            globals()[_name] = getattr(_canon, _name)
except Exception:  # pragma: no cover
    pass


def compute_tda_for_ticker(*args: Any, **kwargs: Any):
    from src.structural.tda_indicators import compute_tda_for_ticker as _impl  # type: ignore
    return _impl(*args, **kwargs)


def compute_tda_context(*args: Any, **kwargs: Any):
    from src.structural.tda_indicators import compute_tda_context as _impl  # type: ignore
    return _impl(*args, **kwargs)


def build_tda_context_markdown(*args: Any, **kwargs: Any):
    from src.structural.tda_indicators import build_tda_context_markdown as _impl  # type: ignore
    return _impl(*args, **kwargs)


def build_tda_metrics_df(*args: Any, **kwargs: Any):
    from src.structural.tda_indicators import build_tda_metrics_df as _impl  # type: ignore
    return _impl(*args, **kwargs)


__all__ = [
    "compute_tda_for_ticker",
    "compute_tda_context",
    "build_tda_context_markdown",
    "build_tda_metrics_df",
]
