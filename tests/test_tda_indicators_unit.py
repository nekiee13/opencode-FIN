from __future__ import annotations

import numpy as np
import pandas as pd


def _make_close_df(n: int, *, constant: bool = False) -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-02", periods=n, freq="B")
    if constant:
        close = np.full(n, 100.0, dtype=float)
    else:
        close = np.linspace(100.0, 120.0, n, dtype=float) + 0.3 * np.sin(
            np.arange(n, dtype=float) / 4.0
        )
    return pd.DataFrame({"Close": close}, index=idx)


def test_tda_state_missing_dep(monkeypatch) -> None:
    from src.structural import tda_indicators as tda

    monkeypatch.setattr(tda, "_tda_enabled", lambda: False)
    monkeypatch.setattr(tda, "_get_ripser_func", lambda: None)

    ctxs, md, df = tda.compute_tda_context({"AAA": _make_close_df(130)})
    assert len(ctxs) == 1
    assert tda._state_to_str(ctxs[0].state) == "MISSING_DEP"
    assert "State: MISSING_DEP" in md
    assert str(df.loc[0, "State"]) == "MISSING_DEP"


def test_tda_state_insufficient_data() -> None:
    from src.structural import tda_indicators as tda

    ctxs, md, df = tda.compute_tda_context({"AAA": _make_close_df(8)})
    assert len(ctxs) == 1
    assert tda._state_to_str(ctxs[0].state) == "INSUFFICIENT_DATA"
    assert "State: INSUFFICIENT_DATA" in md
    assert str(df.loc[0, "State"]) == "INSUFFICIENT_DATA"


def test_tda_state_degenerate(monkeypatch) -> None:
    from src.structural import tda_indicators as tda

    def _dummy_ripser(*args, **kwargs):
        return {"dgms": [np.empty((0, 2)), np.empty((0, 2))]}

    monkeypatch.setattr(tda, "_tda_enabled", lambda: True)
    monkeypatch.setattr(tda, "_get_ripser_func", lambda: _dummy_ripser)

    ctxs, md, df = tda.compute_tda_context({"AAA": _make_close_df(130, constant=True)})
    assert len(ctxs) == 1
    assert tda._state_to_str(ctxs[0].state) == "DEGENERATE"
    assert "State: DEGENERATE" in md
    assert str(df.loc[0, "State"]) == "DEGENERATE"


def test_tda_ok_empty_h1_diagram_returns_zero_metrics(monkeypatch) -> None:
    from src.structural import tda_indicators as tda

    def _fake_ripser(*args, **kwargs):
        return {
            "dgms": [
                np.asarray([[0.0, 1.0]], dtype=float),
                np.empty((0, 2), dtype=float),
            ]
        }

    monkeypatch.setattr(tda, "_tda_enabled", lambda: True)
    monkeypatch.setattr(tda, "_get_ripser_func", lambda: _fake_ripser)

    ctxs, md, df = tda.compute_tda_context({"AAA": _make_close_df(130)})
    assert len(ctxs) == 1
    c = ctxs[0]
    assert tda._state_to_str(c.state) == "OK"
    assert c.h1_max_persist == 0.0
    assert c.h1_count_above_thr == 0.0
    assert c.h1_entropy == 0.0
    assert "State: OK" in md
    assert float(df.loc[0, "H1_MaxPersistence"]) == 0.0
    assert float(df.loc[0, "H1_CountAbove_Thr"]) == 0.0
    assert float(df.loc[0, "H1_Entropy"]) == 0.0


def test_tda_error_state_truncates_message(monkeypatch) -> None:
    from src.structural import tda_indicators as tda

    long_msg = "E" * 1000

    def _boom(*args, **kwargs):
        raise RuntimeError(long_msg)

    monkeypatch.setattr(tda, "_tda_enabled", lambda: True)
    monkeypatch.setattr(tda, "_get_ripser_func", lambda: _boom)

    ctxs, md, df = tda.compute_tda_context({"AAA": _make_close_df(130)})
    assert len(ctxs) == 1
    c = ctxs[0]
    assert tda._state_to_str(c.state) == "ERROR"
    assert c.notes
    first_note = str(c.notes[0])
    assert len(first_note) < 300
    assert "..." in first_note
    assert "State: ERROR" in md
    assert str(df.loc[0, "State"]) == "ERROR"
