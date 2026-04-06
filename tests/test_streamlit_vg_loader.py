from __future__ import annotations

import types
import sqlite3
from pathlib import Path

from src.ui.services.vg_loader import (
    format_blue_table_rows,
    format_green_table_rows,
    format_violet_blue_rows,
    green_meta_to_rows,
    list_violet_forecast_dates,
    materialize_for_selected_date,
    matrix_to_rows,
    next_business_day,
    pick_anchored_violet_date,
    resolve_target_forecast_date,
    suggest_forecast_date,
)


def test_next_business_day_skips_weekend() -> None:
    assert next_business_day("2026-03-27") == "2026-03-30"


def test_resolve_target_forecast_date_uses_fh3_asof_cutoff(tmp_path: Path) -> None:
    fh3_dir = tmp_path / "fh3"
    fh3_dir.mkdir(parents=True, exist_ok=True)
    path = fh3_dir / "FH3_TABLE_FULL_20260326.csv"
    path.write_text(
        "\n".join(
            [
                "Ticker,FilePrefix,Last_Close_ASOF,Model_Used,Col_Used,FH_Date1,FH_Day1,FH_Date2,FH_Day2,FH_Date3,FH_Day3,Run_Mode,AsOf_Cutoff",
                "TNX,TNX,1,DYNAMIX,DYNAMIX_Pred,2026-03-26,1,2026-03-27,1,2026-03-30,1,replay,2026-03-24",
                "DJI,DJI,1,DYNAMIX,DYNAMIX_Pred,2026-03-26,1,2026-03-27,1,2026-03-30,1,replay,2026-03-24",
                "SPX,GSPC,1,DYNAMIX,DYNAMIX_Pred,2026-03-26,1,2026-03-27,1,2026-03-30,1,replay,2026-03-24",
                "VIX,VIX,1,DYNAMIX,DYNAMIX_Pred,2026-03-26,1,2026-03-27,1,2026-03-30,1,replay,2026-03-24",
                "QQQ,QQQ,1,DYNAMIX,DYNAMIX_Pred,2026-03-26,1,2026-03-27,1,2026-03-30,1,replay,2026-03-24",
                "AAPL,AAPL,1,DYNAMIX,DYNAMIX_Pred,2026-03-26,1,2026-03-27,1,2026-03-30,1,replay,2026-03-24",
                "",
            ]
        ),
        encoding="utf-8",
    )

    out = resolve_target_forecast_date(
        selected_date="2026-03-24",
        fh3_dir=fh3_dir,
    )
    assert out == "2026-03-26"


def test_resolve_target_forecast_date_falls_back_to_selected_date() -> None:
    out = resolve_target_forecast_date(selected_date="2026-03-24")
    assert out == "2026-03-24"


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


def test_materialize_for_selected_date_resolves_from_fh3_when_forecast_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
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

    fh3_dir = tmp_path / "fh3"
    fh3_dir.mkdir(parents=True, exist_ok=True)
    (fh3_dir / "FH3_TABLE_FULL_20260326.csv").write_text(
        "\n".join(
            [
                "Ticker,FilePrefix,Last_Close_ASOF,Model_Used,Col_Used,FH_Date1,FH_Day1,FH_Date2,FH_Day2,FH_Date3,FH_Day3,Run_Mode,AsOf_Cutoff",
                "TNX,TNX,1,DYNAMIX,DYNAMIX_Pred,2026-03-26,1,2026-03-27,1,2026-03-30,1,replay,2026-03-24",
                "",
            ]
        ),
        encoding="utf-8",
    )

    out = materialize_for_selected_date(
        selected_date="2026-03-24",
        fh3_dir=fh3_dir,
    )

    assert out == {"ok": True}
    assert captured["forecast_date"] == "2026-03-26"


def test_list_violet_forecast_dates_returns_descending(tmp_path: Path) -> None:
    db_path = tmp_path / "ML_VG_tables.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE violet_scores (
                forecast_date TEXT,
                model TEXT,
                ticker TEXT,
                accuracy_pct REAL,
                score_status TEXT,
                source_round_id TEXT,
                source_partial_scores_path TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO violet_scores(forecast_date, model, ticker, accuracy_pct, score_status, source_round_id, source_partial_scores_path, created_at, updated_at)
            VALUES ('2025-08-05', 'Torch', 'TNX', 95.0, 'scored', 'r1', 'x', 't', 't')
            """
        )
        conn.execute(
            """
            INSERT INTO violet_scores(forecast_date, model, ticker, accuracy_pct, score_status, source_round_id, source_partial_scores_path, created_at, updated_at)
            VALUES ('2025-07-29', 'Torch', 'TNX', 94.0, 'scored', 'r0', 'x', 't', 't')
            """
        )
        conn.commit()
    finally:
        conn.close()

    out = list_violet_forecast_dates(db_path)
    assert out == ["2025-08-05", "2025-07-29"]


def test_suggest_forecast_date_uses_nearest_prior() -> None:
    out = suggest_forecast_date(
        selected_date="2026-04-01",
        available_dates=["2026-03-31", "2026-03-24", "2026-03-17"],
    )
    assert out == "2026-03-31"


def test_pick_anchored_violet_date_prefers_selected_date() -> None:
    out = pick_anchored_violet_date(
        selected_date="2026-02-27",
        available_dates=["2026-02-27", "2026-03-02"],
    )
    assert out == "2026-02-27"


def test_pick_anchored_violet_date_uses_target_when_selected_missing(
    tmp_path: Path,
) -> None:
    fh3_dir = tmp_path / "fh3"
    fh3_dir.mkdir(parents=True, exist_ok=True)
    (fh3_dir / "FH3_TABLE_FULL_20260302.csv").write_text(
        "\n".join(
            [
                "Ticker,FilePrefix,Last_Close_ASOF,Model_Used,Col_Used,FH_Date1,FH_Day1,FH_Date2,FH_Day2,FH_Date3,FH_Day3,Run_Mode,AsOf_Cutoff",
                "TNX,TNX,1,DYNAMIX,DYNAMIX_Pred,2026-03-02,1,2026-03-03,1,2026-03-04,1,replay,2026-02-27",
                "",
            ]
        ),
        encoding="utf-8",
    )

    out = pick_anchored_violet_date(
        selected_date="2026-02-27",
        available_dates=["2026-03-02"],
        fh3_dir=fh3_dir,
    )
    assert out == "2026-03-02"


def test_pick_anchored_violet_date_returns_none_when_unrelated() -> None:
    out = pick_anchored_violet_date(
        selected_date="2025-07-29",
        available_dates=["2026-02-27"],
    )
    assert out is None


def test_format_green_table_rows_uses_three_decimals() -> None:
    rows = [
        {"Ticker": "TNX", "Torch": 99.1, "ARIMAX": 7, "PCE": None},
        {"Ticker": "AAPL", "Torch": 9.87654, "ARIMAX": "10.5", "PCE": ""},
    ]
    out = format_green_table_rows(rows)
    assert out[0]["Torch"] == "99.100"
    assert out[0]["ARIMAX"] == "07.000"
    assert out[0]["PCE"] is None
    assert out[1]["Torch"] == "09.877"
    assert out[1]["ARIMAX"] == "10.500"
    assert out[1]["PCE"] is None


def test_format_violet_blue_rows_replaces_none_with_unavailable_label() -> None:
    rows = [
        {"Ticker": "TNX", "Torch": 99.1, "LSTM": None, "VAR": ""},
        {"Ticker": "AAPL", "Torch": None, "LSTM": 98.5, "VAR": 97.0},
    ]
    out = format_violet_blue_rows(rows)
    assert out[0]["Torch"] == 99.1
    assert out[0]["LSTM"] == "model_unavailable"
    assert out[0]["VAR"] == "model_unavailable"
    assert out[1]["Torch"] == "model_unavailable"
    assert out[1]["LSTM"] == 98.5


def test_format_blue_table_rows_formats_two_decimals_and_labels_missing() -> None:
    rows = [
        {"Ticker": "TNX", "Torch": 99.2687, "LSTM": None, "VAR": ""},
        {"Ticker": "AAPL", "Torch": "98.7", "LSTM": "model_unavailable", "VAR": 100},
    ]
    out = format_blue_table_rows(rows)
    assert out[0]["Torch"] == "99.27"
    assert out[0]["LSTM"] == "model_unavailable"
    assert out[0]["VAR"] == "model_unavailable"
    assert out[1]["Torch"] == "98.70"
    assert out[1]["LSTM"] == "model_unavailable"
    assert out[1]["VAR"] == "100.00"
