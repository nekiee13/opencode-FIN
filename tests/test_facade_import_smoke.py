# ------------------------
# tests\test_facade_import_smoke.py
# ------------------------
# tests/test_facade_import_smoke.py
from __future__ import annotations

import builtins
import importlib
import os
import sys
from pathlib import Path
from typing import Sequence

import pytest


BLOCKED_IMPORT_ROOTS = {
    "pmdarima",
    "statsmodels",
    "arch",
    "tensorflow",
    "keras",
    "torch",
    "sklearn",
    "xgboost",
    "lightgbm",
    "catboost",
    "pycaret",
}


class _BlockImportsFinder:
    def __init__(self, blocked_roots: set[str]):
        self._blocked = blocked_roots

    def find_spec(self, fullname: str, path, target=None):  # type: ignore[override]
        root = fullname.split(".")[0]
        if root in self._blocked:
            raise ModuleNotFoundError(f"Blocked optional dependency import: {root}")
        return None


class _NoFsWrites:
    def __init__(self, monkeypatch: pytest.MonkeyPatch):
        self.mp = monkeypatch

    def __enter__(self):
        self.mp.setattr(os, "makedirs", _raise_fs("os.makedirs"), raising=True)
        self.mp.setattr(Path, "mkdir", _raise_fs("Path.mkdir"), raising=True)
        self.mp.setattr(builtins, "open", _guarded_open, raising=True)

        import shutil

        self.mp.setattr(shutil, "copy", _raise_fs("shutil.copy"), raising=True)
        self.mp.setattr(shutil, "copy2", _raise_fs("shutil.copy2"), raising=True)
        self.mp.setattr(shutil, "move", _raise_fs("shutil.move"), raising=True)
        self.mp.setattr(shutil, "rmtree", _raise_fs("shutil.rmtree"), raising=True)
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _raise_fs(api: str):
    def _inner(*args, **kwargs):
        raise AssertionError(f"Import-time filesystem mutation is forbidden during Phase-1: attempted {api}")

    return _inner


_ORIG_OPEN = builtins.open


def _guarded_open(file, mode="r", *args, **kwargs):
    if any(m in str(mode) for m in ("w", "a", "x", "+")):
        raise AssertionError(
            f"Import-time filesystem writes are forbidden during Phase-1: open({file!r}, mode={mode!r})"
        )
    return _ORIG_OPEN(file, mode, *args, **kwargs)


def _purge_modules(prefixes: Sequence[str]) -> None:
    to_del = [m for m in list(sys.modules.keys()) if any(m == p or m.startswith(p + ".") for p in prefixes)]
    for m in to_del:
        del sys.modules[m]


def test_facade_import_smoke_no_optional_deps_no_fs_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    _purge_modules(["src", "src.models", "src.models.facade"])

    finder = _BlockImportsFinder(BLOCKED_IMPORT_ROOTS)
    sys.meta_path.insert(0, finder)

    try:
        with _NoFsWrites(monkeypatch):
            mod = importlib.import_module("src.models.facade")
        assert mod is not None
        assert hasattr(mod, "ForecastArtifact"), "src.models.facade must define ForecastArtifact"
    finally:
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass


def test_forecastartifact_contract_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    import pandas as pd

    with _NoFsWrites(monkeypatch):
        from src.models.facade import ForecastArtifact

    idx = pd.date_range("2025-01-01", periods=3, freq="D")
    df = pd.DataFrame({"yhat": [1.0, 2.0, 3.0]}, index=idx)

    art = ForecastArtifact(pred_df=df, pred_col="yhat")
    assert art.pred_col == "yhat"
    assert art.pred_df.index.equals(idx)
