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

        return _main(*args, **kwargs)
    except Exception:
        # Fallback: if src.ui.gui does not expose main(), attempt to run app directly.
        if StockAnalysisApp is None:
            raise

        # Keep entrypoint smoke non-interactive under pytest.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return None

        import tkinter as tk  # stdlib

        try:
            root = tk.Tk()
        except Exception:
            return None
        StockAnalysisApp(root)  # type: ignore[misc]
        root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["StockAnalysisApp", "main"]
