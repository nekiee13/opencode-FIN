# ------------------------
# structural\__init__.py
# ------------------------
"""
FIN structural analysis package.

Purpose
-------
Provides structural-context indicators used for regime analysis, sentiment
validation, and higher-level narrative consistency checks.

Contents
--------
- svl_indicators : SVL-v1.0 structural indicators (Hurst, regimes, fractals, trends)
- tda_indicators : TDA Phase 2A indicators (persistent homology–based structure)

Design
------
- Side-effect free on import.
- Heavy or optional dependencies are gated inside submodules.
"""

from __future__ import annotations

from .svl_indicators import (
    TickerStructuralContext,
    export_structural_context_markdown,
    export_metrics_csv,
)

__all__ = [
    "TickerStructuralContext",
    "export_structural_context_markdown",
    "export_metrics_csv",
]
