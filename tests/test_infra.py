# ------------------------
# tests/test_infra.py
# ------------------------
"""
Infrastructure and import-safety tests for FIN.

Goals
-----
- Validate that core modules import without side effects and without requiring optional dependencies.
- Validate lazy submodule loading behavior for src.models.__init__ (if implemented).
- Validate canonical CSV loading/sanitization in src.data.loading.
- Validate utility helpers (pivots) operate on minimal, well-formed inputs.

Run
---
pytest -q
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _write_minimal_ohlcv_csv(
    path: Path,
    *,
    date_col: str = "Date",
    rows: int = 5,
    with_volume: bool = True,
) -> None:
    """
    Create a minimal OHLCV CSV in the legacy-preferred date format '%b %d, %Y'.
    """
    base = pd.Timestamp("2025-01-02")
    dates = [(base + pd.Timedelta(days=i)).strftime("%b %d, %Y") for i in range(rows)]

    data: Dict[str, Any] = {
        date_col: dates,
        "Open": np.linspace(10.0, 10.0 + rows - 1, rows),
        "High": np.linspace(10.5, 10.5 + rows - 1, rows),
        "Low": np.linspace(9.5, 9.5 + rows - 1, rows),
        "Close": np.linspace(10.2, 10.2 + rows - 1, rows),
    }
    if with_volume:
        data["Volume"] = np.linspace(1000, 1000 + 10 * (rows - 1), rows).astype(int)

    df = pd.DataFrame(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _has_module(modname: str) -> bool:
    try:
        importlib.import_module(modname)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------
# Import safety
# ---------------------------------------------------------------------


def test_import_src_models_package_has_no_eager_model_imports() -> None:
    """
    Importing src.models should not eagerly import model submodules.
    """
    for k in list(sys.modules.keys()):
        if k == "src.models" or k.startswith("src.models."):
            sys.modules.pop(k, None)

    m = importlib.import_module("src.models")
    assert m is not None

    # Best-effort check: common submodules should not be present after package import.
    assert "src.models.var" not in sys.modules
    assert "src.models.random_walk" not in sys.modules


def test_models_lazy_attribute_access_imports_submodule() -> None:
    """
    If lazy attribute access is implemented, getattr(src.models, 'var') should import src.models.var.
    If not implemented or submodule not present, the test is skipped.
    """
    for k in list(sys.modules.keys()):
        if k == "src.models" or k.startswith("src.models."):
            sys.modules.pop(k, None)

    m = importlib.import_module("src.models")
    assert "src.models.var" not in sys.modules

    try:
        _ = getattr(m, "var")
    except AttributeError:
        pytest.skip("src.models.var attribute not exposed via lazy import in src.models.__init__.")
        return

    assert "src.models.var" in sys.modules


def test_import_loading_module() -> None:
    """
    src.data.loading should import without requiring external services.
    """
    mod = importlib.import_module("src.data.loading")
    assert hasattr(mod, "fetch_data")
    assert hasattr(mod, "resolve_raw_csv_path")
    assert hasattr(mod, "normalize_ohlcv_columns")


# ---------------------------------------------------------------------
# src.data.loading behavior
# ---------------------------------------------------------------------


def test_fetch_data_missing_file_returns_none(tmp_path: Path) -> None:
    """
    fetch_data should return None on missing CSV.
    """
    from src.data.loading import fetch_data

    missing = tmp_path / "nope.csv"
    df = fetch_data("AAPL", csv_path=missing)
    assert df is None


def test_fetch_data_parses_legacy_date_format_and_normalizes_columns(tmp_path: Path) -> None:
    """
    Verifies:
    - Legacy '%b %d, %Y' date parsing succeeds
    - DatetimeIndex is produced
    - OHLC columns exist and are numeric
    - Index is sorted ascending
    """
    from src.data.loading import fetch_data

    csv_path = tmp_path / "AAPL_data.csv"
    _write_minimal_ohlcv_csv(csv_path, date_col="Date", rows=8, with_volume=True)

    df = fetch_data("AAPL", csv_path=csv_path)
    assert df is not None
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing

    for c in ("Open", "High", "Low", "Close"):
        assert c in df.columns
        assert pd.api.types.is_numeric_dtype(df[c])

    assert len(df) >= 5


def test_fetch_data_handles_duplicate_dates_keeps_last(tmp_path: Path) -> None:
    """
    Duplicate date rows should be reduced to a unique DatetimeIndex, keeping the last occurrence.
    """
    from src.data.loading import fetch_data

    csv_path = tmp_path / "DJI_data.csv"
    _write_minimal_ohlcv_csv(csv_path, date_col="Date", rows=3, with_volume=False)

    # Append a duplicate date with different Close (should be kept).
    df0 = pd.read_csv(csv_path)
    dup = df0.iloc[-1].copy()
    dup["Close"] = float(dup["Close"]) + 100.0
    df1 = pd.concat([df0, pd.DataFrame([dup])], ignore_index=True)
    df1.to_csv(csv_path, index=False)

    df = fetch_data("DJI", csv_path=csv_path)
    assert df is not None

    # Must remain at 3 unique dates after deduplication.
    assert len(df) == 3
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_unique

    # Scalar-safe extraction for static typing: .at requires a unique index.
    last_dt = df.index.max()
    last_close = float(df.at[last_dt, "Close"])
    assert last_close > 50.0


# ---------------------------------------------------------------------
# src.utils.pivots behavior
# ---------------------------------------------------------------------


def test_pivots_calculate_latest_pivot_points_minimal() -> None:
    """
    Pivot calc should return a PivotCalcResult for a minimal 2-row OHLC DataFrame.
    """
    from src.utils.pivots import PivotCalcResult, calculate_latest_pivot_points

    idx = pd.to_datetime(["2025-01-02", "2025-01-03"])
    df = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [10.5, 11.5],
            "Low": [9.5, 10.5],
            "Close": [10.2, 11.2],
            "Volume": [1000, 1100],
        },
        index=idx,
    )

    res = calculate_latest_pivot_points(df)
    assert res is not None
    assert isinstance(res, PivotCalcResult)
    assert isinstance(res.asof_date, pd.Timestamp)
    assert isinstance(res.based_on_date, pd.Timestamp)
    assert "Classic" in res.pivot_data
    assert "Pivot" in res.pivot_data["Classic"]


# ---------------------------------------------------------------------
# Optional dependency sanity checks (skip if not installed)
# ---------------------------------------------------------------------


def test_optional_statsmodels_import_guard() -> None:
    """
    If statsmodels is installed, src.models.var should import successfully.
    """
    if not _has_module("statsmodels"):
        pytest.skip("statsmodels not installed; optional dependency test skipped.")
    mod = importlib.import_module("src.models.var")
    assert mod is not None


def test_optional_chaospy_import_guard() -> None:
    """
    If chaospy is installed, src.models.pce_narx should import successfully.
    """
    if not _has_module("chaospy"):
        pytest.skip("chaospy not installed; optional dependency test skipped.")
    mod = importlib.import_module("src.models.pce_narx")
    assert mod is not None
