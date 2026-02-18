# ------------------------
# compat\StructuralIndicators.py
# ------------------------
"""
FIN StructuralIndicators legacy facade (compat layer).


Location
--------
compat/StructuralIndicators.py


Purpose
-------
Preserve legacy imports used by transitional scripts (e.g., scripts/svl_export.py):


from compat.StructuralIndicators import ...


This module re-exports the canonical implementation from:
src.structural.svl_indicators


Refactor policy
---------------
- No behavior changes are introduced here.
- All implementation lives in src/structural/svl_indicators.py.
"""


from __future__ import annotations


from src.structural.svl_indicators import ( # noqa: F401
# Data structures
WilliamsSignal,
HurstPack,
TickerStructuralContext,
# Constants
HURST_THRESH_PERSISTENT,
HURST_THRESH_MEANREVERT,
TREND10D_UP_THRESH,
TREND10D_DOWN_THRESH,
H20_HISTORY_LEN,
WILLIAMS_CONFIRM_LAG,
WILLIAMS_LOOKBACK_CONFIRMED,
# Core functions
normalize_ohlcv_columns,
load_ohlcv_from_csv,
load_ohlcv_from_yfinance,
compute_structural_context_for_ticker,
export_structural_context_markdown,
export_metrics_csv,
)


__all__ = [
"WilliamsSignal",
"HurstPack",
"TickerStructuralContext",
"HURST_THRESH_PERSISTENT",
"HURST_THRESH_MEANREVERT",
"TREND10D_UP_THRESH",
"TREND10D_DOWN_THRESH",
"H20_HISTORY_LEN",
"WILLIAMS_CONFIRM_LAG",
"WILLIAMS_LOOKBACK_CONFIRMED",
"normalize_ohlcv_columns",
"load_ohlcv_from_csv",
"load_ohlcv_from_yfinance",
"compute_structural_context_for_ticker",
"export_structural_context_markdown",
"export_metrics_csv",
]
