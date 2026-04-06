from __future__ import annotations

from pathlib import Path

from src.ui.services.dashboard_loader import (
    build_marker_comparison_rows,
    load_marker_values,
    load_model_table,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_model_table_uses_round_asof_date(tmp_path: Path) -> None:
    rounds_dir = tmp_path / "rounds"
    csv_path = rounds_dir / "26-1-99" / "t0_forecasts.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "round_id,round_state,ticker,runtime_ticker,model,fh_step,forecast_date,pred_value,lower_ci,upper_ci,status,generated_at",
                "26-1-99,DRAFT_T0,TNX,TNX,Torch,1,2026-03-25,4.0700,3.99,4.15,ok,2026-03-24 08:00:00",
                "26-1-99,DRAFT_T0,TNX,TNX,Torch,3,2026-03-27,4.0900,3.99,4.15,ok,2026-03-24 08:00:00",
                "26-1-99,DRAFT_T0,TNX,TNX,ARIMAX,3,2026-03-27,4.2400,4.21,4.27,ok,2026-03-24 08:00:00",
                "26-1-99,DRAFT_T0,AAPL,AAPL,Torch,1,2026-03-25,251.00,249.0,253.0,ok,2026-03-24 08:00:00",
                "26-1-99,DRAFT_T0,AAPL,AAPL,Torch,3,2026-03-27,253.70,249.0,253.0,ok,2026-03-24 08:00:00",
                "",
            ]
        ),
    )

    table = load_model_table("2026-03-24", rounds_dir=rounds_dir)
    assert table.source_round_id == "26-1-99"
    assert len(table.rows) == 2
    tnx = next(row for row in table.rows if row["Ticker"] == "TNX")
    assert str(tnx["Torch"]) == "3.990-4.150 ~4.090"
    assert str(tnx["ARIMAX"]) == "4.210-4.270 ~4.240"
    aapl = next(row for row in table.rows if row["Ticker"] == "AAPL")
    assert str(aapl["Torch"]) == "249.00-253.00 ~253.70"


def test_load_model_table_returns_empty_when_selected_before_available_rounds(
    tmp_path: Path,
) -> None:
    rounds_dir = tmp_path / "rounds"
    csv_path = rounds_dir / "26-1-99" / "t0_forecasts.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "round_id,round_state,ticker,runtime_ticker,model,fh_step,forecast_date,pred_value,lower_ci,upper_ci,status,generated_at",
                "26-1-99,DRAFT_T0,TNX,TNX,Torch,1,2026-03-25,4.0700,3.99,4.15,ok,2026-03-24 08:00:00",
                "",
            ]
        ),
    )

    table = load_model_table("2025-07-29", rounds_dir=rounds_dir)
    assert table.source_round_id is None
    assert table.asof_date is None
    assert table.rows == []


def test_load_marker_values_for_selected_date(tmp_path: Path) -> None:
    markers_dir = tmp_path / "markers"
    _write(
        markers_dir / "oraclum.csv",
        "\n".join(
            [
                "Date,TNX,DJI,SPX,VIX,QQQ,AAPL",
                '"Mar 24, 2026",4.289,46339.26,6528.53,25.25,577.22,253.76',
                '"Mar 31, 2026",4.300,46400.00,6530.00,25.20,578.00,254.00',
            ]
        )
        + "\n",
    )

    out = load_marker_values("2026-03-24", markers_dir=markers_dir)
    assert "oraclum" in out
    assert out["oraclum"]["TNX"] == 4.289
    assert out["oraclum"]["AAPL"] == 253.76


def test_load_marker_values_falls_back_to_latest_prior_date(tmp_path: Path) -> None:
    markers_dir = tmp_path / "markers"
    _write(
        markers_dir / "oraclum.csv",
        "\n".join(
            [
                "Date,TNX,DJI,SPX,VIX,QQQ,AAPL",
                '"Feb 24, 2026",4.289,46339.26,6528.53,25.25,577.22,253.76',
                '"Mar 03, 2026",4.300,46400.00,6530.00,25.20,578.00,254.00',
            ]
        )
        + "\n",
    )

    out = load_marker_values("2026-02-27", markers_dir=markers_dir)
    assert "oraclum" in out
    assert out["oraclum"]["TNX"] == 4.289
    assert out["oraclum"]["AAPL"] == 253.76


def test_build_marker_comparison_rows_applies_ticker_formats() -> None:
    model_rows = [
        {"Ticker": "TNX", "Torch": "4.392"},
        {"Ticker": "DJI", "Torch": "46124.06"},
        {"Ticker": "SPX", "Torch": "6537.8"},
        {"Ticker": "VIX", "Torch": "25.5"},
        {"Ticker": "QQQ", "Torch": "581.8"},
        {"Ticker": "AAPL", "Torch": "251"},
    ]
    marker_values: dict[str, dict[str, float | None]] = {
        "oraclum": {
            "TNX": 4.289,
            "DJI": 46339.26,
            "SPX": 6528.53,
            "VIX": 25.25,
            "QQQ": 577.22,
            "AAPL": 253.76,
        },
        "rd": {
            "TNX": 4.33,
            "DJI": 45703.0,
            "SPX": 6537.0,
            "VIX": 25.55,
            "QQQ": 581.8,
            "AAPL": 251.0,
        },
        "85220": {
            "TNX": 4.32,
            "DJI": 45632.0,
            "SPX": 6525.0,
            "VIX": 25.15,
            "QQQ": 580.6,
            "AAPL": 250.5,
        },
    }

    rows = build_marker_comparison_rows(
        model_rows=model_rows,
        marker_values=marker_values,
    )

    by_ticker = {row["Ticker"]: row for row in rows}
    assert by_ticker["TNX"]["ML"] == "4.392"
    assert by_ticker["DJI"]["ML"] == "46124.1"
    assert by_ticker["SPX"]["ML"] == "6537.8"
    assert by_ticker["VIX"]["ML"] == "25.50"
    assert by_ticker["QQQ"]["ML"] == "581.80"
    assert by_ticker["AAPL"]["ML"] == "251.00"
