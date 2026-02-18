# tests/test_app3g_smoke.py
from __future__ import annotations

import importlib.util
import os
import runpy
from pathlib import Path

import pytest


def test_app3g_import_and_startup_smoke() -> None:
    """
    Phase-1 smoke test:
    - app3G.py must be runnable to the point that imports and top-level init do not crash.
    - Forecasting correctness is out of scope for this test.
    """
    repo_root = Path(__file__).resolve().parents[1]
    entry = repo_root / "app3G.py"
    assert entry.exists(), f"Expected entrypoint at {entry}"

    if importlib.util.find_spec("tkinter") is None:
        pytest.skip("tkinter not available in this environment")

    old_cwd = os.getcwd()
    try:
        os.chdir(str(repo_root))
        try:
            runpy.run_path(str(entry), run_name="__main__")
        except SystemExit as e:
            code = getattr(e, "code", 0)
            if isinstance(code, int) and code not in (0, None):
                raise
    finally:
        os.chdir(old_cwd)
