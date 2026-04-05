from __future__ import annotations

from src.ui.services.vg_loader import matrix_to_rows, next_business_day


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
