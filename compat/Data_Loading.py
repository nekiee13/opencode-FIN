# ------------------------
# compat\Data_Loading.py
# ------------------------
"""
FIN legacy Data_Loading facade (compat layer).

Location: compat/Data_Loading.py

Purpose
-------
Preserve the legacy function name and behavior:
    fetch_data(ticker) -> DataFrame|None

Implementation
--------------
Delegates to src.data.loading.fetch_data while keeping the legacy signature.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from src.data.loading import fetch_data as _fetch_data


def fetch_data(ticker: str) -> Optional[pd.DataFrame]:
    return _fetch_data(ticker)


__all__ = ["fetch_data"]
