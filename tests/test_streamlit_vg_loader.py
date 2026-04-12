from __future__ import annotations

import types
import sqlite3
from pathlib import Path

from src.ui.services.vg_loader import (
    build_ann_real_vs_computed_rows,
    build_ann_t0_p_sgn_rows,
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


def test_resolve_target_forecast_date_falls_back_to_selected_date(
    tmp_path: Path,
) -> None:
    fh3_dir = tmp_path / "fh3_empty"
    fh3_dir.mkdir(parents=True, exist_ok=True)
    out = resolve_target_forecast_date(selected_date="2026-03-24", fh3_dir=fh3_dir)
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


def test_build_ann_t0_p_sgn_rows_uses_selected_date_and_round_data(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "TNX_data.csv").write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        '"Mar 31, 2026",4.3000,4.3300,4.2800,4.3110,4.3110,-\n',
        encoding="utf-8",
    )
    (raw_dir / "GSPC_data.csv").write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        '"Mar 31, 2026",6500.0,6510.0,6490.0,6500.0,6500.0,-\n',
        encoding="utf-8",
    )

    rounds_dir = tmp_path / "rounds"
    round_dir = rounds_dir / "anchor-20260331"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "t0_day1_weighted_ensemble.csv").write_text(
        "ticker,weighted_ensemble,weights_used_sum\n"
        "TNX,4.3200,1.0\n"
        "SPX,6400.0000,1.0\n",
        encoding="utf-8",
    )
    (round_dir / "actuals_tplus3.csv").write_text(
        "round_id,ticker,runtime_ticker,expected_actual_date,lookup_actual_date,actual_close,status,source_csv\n"
        "anchor-20260331,TNX,TNX,2026-04-01,2026-04-01,4.3300,ok,TNX_data.csv\n"
        "anchor-20260331,SPX,GSPC,2026-04-01,2026-04-01,6600.0000,ok,GSPC_data.csv\n",
        encoding="utf-8",
    )

    rows = build_ann_t0_p_sgn_rows(
        selected_date="2026-03-31",
        tickers=["TNX", "SPX", "QQQ"],
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_dir,
    )
    by_ticker = {str(x["Ticker"]): x for x in rows}

    assert by_ticker["TNX"]["T0"] == "4.3110"
    assert by_ticker["TNX"]["P"] == "4.3200"
    assert by_ticker["TNX"]["+3-day"] == "4.3300"
    assert by_ticker["TNX"]["Delta"] == "0.0100"
    assert by_ticker["TNX"]["SGN"] == "+"
    assert by_ticker["TNX"]["Magnitude"] == "0.0090"

    assert by_ticker["SPX"]["T0"] == "6500.0000"
    assert by_ticker["SPX"]["P"] == "6400.0000"
    assert by_ticker["SPX"]["+3-day"] == "6600.0000"
    assert by_ticker["SPX"]["Delta"] == "0.0000"
    assert by_ticker["SPX"]["SGN"] == "-"
    assert by_ticker["SPX"]["Magnitude"] == "100.0000"

    assert by_ticker["QQQ"]["T0"] == ""
    assert by_ticker["QQQ"]["P"] == ""
    assert by_ticker["QQQ"]["+3-day"] == "N/A"
    assert by_ticker["QQQ"]["Delta"] == "N/A"
    assert by_ticker["QQQ"]["SGN"] == ""
    assert by_ticker["QQQ"]["Magnitude"] == ""


def test_build_ann_real_vs_computed_rows_uses_round_actuals_and_predictions(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "TNX_data.csv").write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        '"Mar 31, 2026",4.3000,4.3300,4.2800,4.3110,4.3110,-\n',
        encoding="utf-8",
    )
    (raw_dir / "GSPC_data.csv").write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        '"Mar 31, 2026",6500.0,6510.0,6490.0,6500.0,6500.0,-\n',
        encoding="utf-8",
    )

    rounds_dir = tmp_path / "rounds"
    round_dir = rounds_dir / "anchor-20260331"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "t0_day1_weighted_ensemble.csv").write_text(
        "ticker,weighted_ensemble,weights_used_sum\n"
        "TNX,4.3200,1.0\n"
        "SPX,6400.0000,1.0\n",
        encoding="utf-8",
    )
    (round_dir / "actuals_tplus3.csv").write_text(
        "round_id,ticker,runtime_ticker,expected_actual_date,lookup_actual_date,actual_close,status,source_csv\n"
        "anchor-20260331,TNX,TNX,2026-04-01,2026-04-01,4.3300,ok,TNX_data.csv\n"
        "anchor-20260331,SPX,GSPC,2026-04-01,2026-04-01,6600.0000,ok,GSPC_data.csv\n",
        encoding="utf-8",
    )

    rows = build_ann_real_vs_computed_rows(
        selected_date="2026-03-31",
        tickers=["TNX", "SPX", "QQQ"],
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_dir,
    )
    by_ticker = {str(x["Ticker"]): x for x in rows}

    assert by_ticker["TNX"] == {
        "Ticker": "TNX",
        "Real SGN": "+",
        "Computed SGN": "+",
        "Real Magnitude": "0.0190",
        "Computed Magnitude": "0.0090",
    }

    assert by_ticker["SPX"] == {
        "Ticker": "SPX",
        "Real SGN": "+",
        "Computed SGN": "-",
        "Real Magnitude": "100.0000",
        "Computed Magnitude": "100.0000",
    }

    assert by_ticker["QQQ"] == {
        "Ticker": "QQQ",
        "Real SGN": "",
        "Computed SGN": "",
        "Real Magnitude": "",
        "Computed Magnitude": "",
    }


def test_build_ann_t0_p_sgn_rows_uses_markers_3_days_fallback_when_round_actual_missing(
    tmp_path: Path, monkeypatch
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "TNX_data.csv").write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        '"Mar 31, 2026",4.3000,4.3300,4.2800,4.3110,4.3110,-\n',
        encoding="utf-8",
    )

    rounds_dir = tmp_path / "rounds"
    round_dir = rounds_dir / "anchor-20260331"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "t0_day1_weighted_ensemble.csv").write_text(
        "ticker,weighted_ensemble,weights_used_sum\nTNX,4.3200,1.0\n",
        encoding="utf-8",
    )
    # Missing TNX actual_close in round file on purpose.
    (round_dir / "actuals_tplus3.csv").write_text(
        "round_id,ticker,runtime_ticker,expected_actual_date,lookup_actual_date,actual_close,status,source_csv\n",
        encoding="utf-8",
    )

    markers_dir = tmp_path / "markers"
    markers_dir.mkdir(parents=True, exist_ok=True)
    (markers_dir / "3_days.csv").write_text(
        'Date,TNX,DJI,SPX,VIX,QQQ,AAPL\n"Mar 31, 2026",4.3300,,,,,\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("src.ui.services.vg_loader.paths.DATA_RAW_DIR", tmp_path)

    rows = build_ann_t0_p_sgn_rows(
        selected_date="2026-03-31",
        tickers=["TNX"],
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_dir,
    )
    assert rows[0]["+3-day"] == "4.3300"
