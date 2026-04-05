from __future__ import annotations

import types
from src.ui.services.vg_loader import (
    green_meta_to_rows,
    materialize_for_selected_date,
    matrix_to_rows,
    next_business_day,
)


def test_next_business_day_skips_weekend() -> None:
    assert next_business_day("2026-03-27") == "2026-03-30"


def test_matrix_to_rows_maps_models_and_tickers() -> None:
    matrix = {
        "Torch": {"TNX": 99.0, "AAPL": 98.5},
        "ARIMAX": {"TNX": 97.0, "AAPL": None},
    }
    rows = matrix_to_rows(
        matrix=matrix, models=["Torch", "ARIMAX"], tickers=["TNX", "AAPL"]
    )
    assert rows[0]["Ticker"] == "TNX"
    assert rows[0]["Torch"] == 99.0
    assert rows[1]["ARIMAX"] is None


def test_green_meta_to_rows_expands_cells() -> None:
    rows = green_meta_to_rows(
        green_meta={
            "Torch": {
                "TNX": {"real_rounds_used": 1, "bootstrap_slots_used": 3},
            }
        },
        models=["Torch"],
        tickers=["TNX"],
    )
    assert rows == [
        {
            "Ticker": "TNX",
            "Model": "Torch",
            "Real Rounds Used": 1,
            "Dummy Slots Used": 3,
        }
    ]


def test_materialize_for_selected_date_passes_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeStore:
        @staticmethod
        def materialize_vbg_for_date(forecast_date: str, **kwargs):
            captured["forecast_date"] = forecast_date
            captured.update(kwargs)
            return {"ok": True}

    import sys

    monkeypatch.setitem(
        sys.modules,
        "src.followup_ml",
        types.SimpleNamespace(vg_store=_FakeStore),
    )

    # call through with explicit forecast date so next_business_day is not used
    out = materialize_for_selected_date(
        selected_date="2026-03-24",
        forecast_date="2026-03-25",
        memory_tail=5,
        bootstrap_enabled=True,
        bootstrap_score=99.0,
        policy_name="value_assign_v1",
    )

    assert out == {"ok": True}
    assert captured["forecast_date"] == "2026-03-25"
    assert captured["memory_tail"] == 5
    assert captured["bootstrap_enabled"] is True
    assert captured["policy_name"] == "value_assign_v1"
