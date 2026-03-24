# ------------------------
# compat/GUI.py
# ------------------------
"""
Legacy GUI (compat layer) — delegation-only.

Phase-1:
- Canonical GUI lives in src.ui.gui
- compat keeps module name stable for legacy scripts
"""

from __future__ import annotations

import os
from typing import Any


# Re-export the canonical app class (legacy code likely imports this name).
try:
    from src.ui.gui import StockAnalysisApp  # type: ignore
except Exception:  # pragma: no cover
    StockAnalysisApp = None  # type: ignore


def main(*args: Any, **kwargs: Any) -> None:
    """
    Standard legacy entrypoint: `python compat/GUI.py`
    Delegates to src.ui.gui.main if available; otherwise starts StockAnalysisApp directly.
    """
    try:
        from src.ui.gui import main as _main  # type: ignore
    except Exception:
        return _run_legacy_fallback(*args, **kwargs)
    return _main(*args, **kwargs)


def _run_legacy_fallback(*args: Any, **kwargs: Any) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    if StockAnalysisApp is None:
        raise RuntimeError("src.ui.gui.StockAnalysisApp is not available")

    analysis_callback = kwargs.get("analysis_callback")
    if analysis_callback is None:
        return None

    import tkinter as tk  # stdlib

    try:
        root = tk.Tk()
    except Exception:
        return None
    StockAnalysisApp(root, analysis_callback=analysis_callback)  # type: ignore[misc]
    root.mainloop()
    return None


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["StockAnalysisApp", "main"]
