from __future__ import annotations

from pathlib import Path

from src.ui.services.dashboard_loader import (
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
    assert "4.0900" in str(tnx["Torch"])
    assert "4.21" in str(tnx["ARIMAX"])


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
