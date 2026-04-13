from __future__ import annotations

from src.ui.services import ann_sgn_compute


def test_predict_ann_computed_sgn_overrides_reuses_ticker_context_cache(
    monkeypatch,
) -> None:
    calls = {"prepare": 0, "evaluate": 0}

    def _fake_prepare(**kwargs):
        calls["prepare"] += 1
        return {"ticker": str(kwargs.get("ticker") or "").upper()}

    def _fake_eval(**kwargs):
        calls["evaluate"] += 1
        context = kwargs.get("context") or {}
        ticker = str(context.get("ticker") or "").upper()
        if ticker == "DJI":
            value = "+1"
        else:
            value = "-1"
        return {"suggested_real_sgn": {"value": value, "confidence": 0.9, "reason": ""}}

    monkeypatch.setattr(
        ann_sgn_compute,
        "prepare_sgn_probability_context",
        _fake_prepare,
    )
    monkeypatch.setattr(
        ann_sgn_compute,
        "evaluate_sgn_suggestion_from_context",
        _fake_eval,
    )

    shared_cache: dict[str, dict[str, object]] = {}

    out1 = ann_sgn_compute.predict_ann_computed_sgn_overrides(
        selected_date="2026-04-07",
        tickers=["DJI", "TNX"],
        compare_rows=[
            {"Ticker": "DJI", "Computed SGN": "-"},
            {"Ticker": "TNX", "Computed SGN": "+"},
        ],
        map_context_cache=shared_cache,
    )
    out2 = ann_sgn_compute.predict_ann_computed_sgn_overrides(
        selected_date="2026-03-31",
        tickers=["DJI", "TNX"],
        compare_rows=[
            {"Ticker": "DJI", "Computed SGN": "-"},
            {"Ticker": "TNX", "Computed SGN": "+"},
        ],
        map_context_cache=shared_cache,
    )

    assert out1["computed_sgn_overrides"]["DJI"] == "-"
    assert out1["computed_sgn_overrides"]["TNX"] == "-"
    assert out2["computed_sgn_overrides"]["DJI"] == "-"
    assert out2["computed_sgn_overrides"]["TNX"] == "-"
    assert calls["prepare"] == 2
    assert calls["evaluate"] == 4
