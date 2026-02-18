# ------------------------
# compat/PCEModel.py
# ------------------------
"""
Legacy PCEModel (compat layer) — delegation-only.

Phase-1 invariants
------------------
- compat/ must not contain modeling logic or heavy imports.
- src/ is canonical implementation.

This module preserves the legacy public API by delegating to src.models.pce_narx.

Pylance stability goals
-----------------------
- Avoid using runtime variables (e.g., pd) inside type expressions.
- Use TYPE_CHECKING imports for pandas typing names.
- Keep runtime import behavior minimal and safe in environments without pandas.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING, cast

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

if TYPE_CHECKING:
    from pandas import DataFrame

# Best-effort re-exports to preserve legacy symbol surface (if provided by canonical impl).
try:  # pragma: no cover
    from src.models import pce_narx as _canon  # type: ignore

    # Common legacy helper names seen in older PCE/NARX scripts; exported only if present.
    _LEGACY_EXPORTS = (
        "_build_narx_dataset_from_df",
        "PCEParams",
        "NARXParams",
        "PCEModelResult",
        "predict_pce_narx",
    )
    for _name in _LEGACY_EXPORTS:
        if hasattr(_canon, _name):
            globals()[_name] = getattr(_canon, _name)
except Exception:  # pragma: no cover
    pass


def predict_pce_narx(
    enriched_data: "DataFrame",
    exog_train_df: Optional["DataFrame"] = None,
    exog_future_df: Optional["DataFrame"] = None,
    progress_callback=None,
) -> Optional["DataFrame"]:
    """Legacy entrypoint preserved; delegates to src.models.pce_narx.predict_pce_narx."""
    if pd is None:
        return None
    if enriched_data is None or getattr(enriched_data, "empty", True):
        return None

    from src.models.pce_narx import predict_pce_narx as _predict  # type: ignore

    out = _predict(
        enriched_data=enriched_data,
        exog_train_df=exog_train_df,
        exog_future_df=exog_future_df,
        progress_callback=progress_callback,
    )
    return None if out is None else cast("DataFrame", out)


__all__ = ["predict_pce_narx"]
