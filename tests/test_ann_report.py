from __future__ import annotations

import json
from pathlib import Path

from src.ui.services.ann_report import (
    build_export_filename,
    export_ann_report_markdown,
    load_ann_report_sections,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_raw(raw_dir: Path) -> None:
    _write(
        raw_dir / "TNX_data.csv",
        "Date,Open,High,Low,Close,Volume\n2026-03-31,4.1,4.2,4.0,4.3110,100\n",
    )


def _seed_round(rounds_dir: Path) -> None:
    round_dir = rounds_dir / "anchor-20260331"
    _write(
        round_dir / "t0_day1_weighted_ensemble.csv",
        "ticker,weighted_ensemble,weights_used_sum\nTNX,4.3200,1.0\n",
    )
    _write(
        round_dir / "actuals_tplus3.csv",
        "round_id,ticker,runtime_ticker,expected_actual_date,lookup_actual_date,actual_close,status,source_csv\n"
        "anchor-20260331,TNX,TNX,2026-04-01,2026-04-01,4.3300,ok,TNX_data.csv\n",
    )


def _seed_setup_and_matrix(out_i_calc_dir: Path) -> None:
    ann_dir = out_i_calc_dir / "ANN"
    _write(
        ann_dir / "TNX.setup.json",
        json.dumps(
            {
                "ticker": "TNX",
                "active": True,
                "model": {"type": "MLP"},
                "training": {"split_policy": "walk_forward", "objective": "dual"},
            }
        ),
    )
    tune_dir = ann_dir / "tuning" / "tune_20260410-170000"
    _write(
        tune_dir / "best_config_matrix.json",
        json.dumps(
            {
                "TNX": {
                    "magnitude": {
                        "status": "healthy",
                        "features_before": 240,
                        "features_after": 120,
                        "r2": 0.82,
                        "mae": 0.20,
                        "rmse": 0.25,
                        "directional_accuracy": 0.75,
                        "learning_rate": 0.001,
                        "epochs": 600,
                        "batch_size": 32,
                        "depth": 2,
                        "width": 32,
                        "dropout": 0.1,
                        "weight_decay": 0.0001,
                        "window_length": 5,
                        "lag_depth": 4,
                    },
                    "sgn": {
                        "status": "fails_baseline",
                        "features_before": 240,
                        "features_after": 120,
                        "r2": 0.99,
                        "mae": 0.01,
                        "rmse": 0.01,
                        "directional_accuracy": 0.60,
                        "learning_rate": 0.001,
                        "epochs": 600,
                        "batch_size": 32,
                        "depth": 2,
                        "width": 32,
                        "dropout": 0.1,
                        "weight_decay": 0.0001,
                        "window_length": 5,
                        "lag_depth": 4,
                    },
                }
            }
        ),
    )


def test_load_ann_report_sections_includes_all_requested_tickers(
    tmp_path: Path,
) -> None:
    out_i_calc_dir = tmp_path / "i_calc"
    rounds_dir = tmp_path / "rounds"
    raw_dir = tmp_path / "raw"
    _seed_raw(raw_dir)
    _seed_round(rounds_dir)
    _seed_setup_and_matrix(out_i_calc_dir)

    payload = load_ann_report_sections(
        selected_date="2026-03-31",
        tickers=["TNX", "DJI"],
        out_i_calc_dir=out_i_calc_dir,
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_dir,
    )

    assert list(payload["sections"].keys()) == ["TNX", "DJI"]
    assert payload["latest_tune_run_id"] == "tune_20260410-170000"


def test_load_ann_report_sections_builds_compare_and_best_setup_rows(
    tmp_path: Path,
) -> None:
    out_i_calc_dir = tmp_path / "i_calc"
    rounds_dir = tmp_path / "rounds"
    raw_dir = tmp_path / "raw"
    _seed_raw(raw_dir)
    _seed_round(rounds_dir)
    _seed_setup_and_matrix(out_i_calc_dir)

    payload = load_ann_report_sections(
        selected_date="2026-03-31",
        tickers=["TNX"],
        out_i_calc_dir=out_i_calc_dir,
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_dir,
    )

    tnx = payload["sections"]["TNX"]
    compare = tnx["compare_row"]
    assert compare["Real SGN"] == "+"
    assert compare["Computed SGN"] == "+"
    assert compare["Real Magnitude"] == "0.0190"
    assert compare["Computed Magnitude"] == "0.0090"

    setup_rows = tnx["best_setup_rows"]
    assert len(setup_rows) == 2
    assert setup_rows[0]["Mode"] == "magnitude"
    assert setup_rows[0]["Epochs"] == 600
    assert setup_rows[0]["Learning Rate"] == 0.001
    assert setup_rows[1]["Mode"] == "sgn"
    assert setup_rows[1]["Status"] == "fails_baseline"


def test_build_export_filename_uses_selected_date_and_ticker_option() -> None:
    name = build_export_filename(selected_date="2025-07-29", selected_ticker="ALL")
    assert name == "Export_report_2025-07-29_ALL.md"

    name_single = build_export_filename(
        selected_date="2025-07-29",
        selected_ticker="tnx",
    )
    assert name_single == "Export_report_2025-07-29_TNX.md"


def test_export_ann_report_markdown_writes_all_scope_file(tmp_path: Path) -> None:
    out_i_calc_dir = tmp_path / "i_calc"
    rounds_dir = tmp_path / "rounds"
    raw_dir = tmp_path / "raw"
    _seed_raw(raw_dir)
    _seed_round(rounds_dir)
    _seed_setup_and_matrix(out_i_calc_dir)

    out = export_ann_report_markdown(
        selected_date="2026-03-31",
        selected_ticker="ALL",
        tickers=["TNX", "DJI"],
        out_i_calc_dir=out_i_calc_dir,
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_dir,
    )

    output_path = Path(str(out["output_path"]))
    assert output_path.name == "Export_report_2026-03-31_ALL.md"
    assert output_path.exists()

    text = output_path.read_text(encoding="utf-8")
    assert "# ANN Report" in text
    assert "## TNX" in text
    assert "## DJI" in text
    assert (
        "| Ticker | Real SGN | Computed SGN | Real Magnitude | Computed Magnitude |"
        in text
    )


def test_export_ann_report_markdown_writes_single_ticker_scope(tmp_path: Path) -> None:
    out_i_calc_dir = tmp_path / "i_calc"
    rounds_dir = tmp_path / "rounds"
    raw_dir = tmp_path / "raw"
    _seed_raw(raw_dir)
    _seed_round(rounds_dir)
    _seed_setup_and_matrix(out_i_calc_dir)

    out = export_ann_report_markdown(
        selected_date="2026-03-31",
        selected_ticker="TNX",
        tickers=["TNX", "DJI"],
        out_i_calc_dir=out_i_calc_dir,
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_dir,
    )

    output_path = Path(str(out["output_path"]))
    assert output_path.name == "Export_report_2026-03-31_TNX.md"
    text = output_path.read_text(encoding="utf-8")
    assert "## TNX" in text
    assert "## DJI" not in text
