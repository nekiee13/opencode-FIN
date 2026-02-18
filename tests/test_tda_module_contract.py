from __future__ import annotations

import importlib
import sys


class _BlockRipserFinder:
    def find_spec(self, fullname: str, path, target=None):  # type: ignore[override]
        if fullname.split(".")[0] == "ripser":
            raise ModuleNotFoundError("Blocked ripser import for contract test")
        return None


def _purge_modules(prefixes: list[str]) -> None:
    to_del = [
        m
        for m in list(sys.modules.keys())
        if any(m == p or m.startswith(p + ".") for p in prefixes)
    ]
    for m in to_del:
        del sys.modules[m]


def test_tda_module_import_without_ripser_and_required_exports() -> None:
    _purge_modules(["src.structural.tda_indicators"])

    finder = _BlockRipserFinder()
    sys.meta_path.insert(0, finder)
    try:
        mod = importlib.import_module("src.structural.tda_indicators")
    finally:
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass

    required = (
        "compute_tda_context",
        "build_tda_context_markdown",
        "build_tda_metrics_df",
    )
    for name in required:
        assert hasattr(mod, name), (
            f"src.structural.tda_indicators missing required export: {name}"
        )
        assert callable(getattr(mod, name)), (
            f"src.structural.tda_indicators export is not callable: {name}"
        )


def test_compute_tda_for_ticker_legacy_adapter_smoke() -> None:
    import pandas as pd

    from src.structural.tda_indicators import compute_tda_for_ticker

    idx = pd.date_range("2026-01-01", periods=8, freq="D")
    close = pd.Series(
        [100.0, 100.5, 101.0, 101.2, 101.1, 101.4, 101.7, 102.0], index=idx
    )

    ctx = compute_tda_for_ticker("TEST", close)
    assert str(ctx.ticker) == "TEST"
    assert hasattr(ctx, "state")
