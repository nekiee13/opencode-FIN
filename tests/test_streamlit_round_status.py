from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.ui.services.round_status import compute_round_status
from src.ui.services.run_registry import append_stage_result, create_run, finalize_run


def _write_ticker_csv(path: Path, rows: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        for date_value, close in rows:
            writer.writerow([date_value, close, close, close, close, 1000])


def _seed_all_tickers(raw_dir: Path) -> None:
    for ticker in ("TNX", "DJI", "GSPC", "VIX", "QQQ", "AAPL"):
        _write_ticker_csv(
            raw_dir / f"{ticker}_data.csv",
            [("2026-03-24", 1.0), ("2026-03-25", 1.1)],
        )


def _seed_violet_score(db_path: Path, forecast_date: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS violet_scores (
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
            INSERT INTO violet_scores(
                forecast_date, model, ticker, accuracy_pct, score_status,
                source_round_id, source_partial_scores_path, created_at, updated_at
            ) VALUES (?, 'Torch', 'TNX', 95.0, 'scored', 'r1', 'x', 't', 't')
            """,
            (forecast_date,),
        )
        conn.commit()
    finally:
        conn.close()


def test_compute_round_status_red_when_data_missing(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "tickers"
    _seed_all_tickers(raw_dir)
    (raw_dir / "AAPL_data.csv").unlink()

    out = compute_round_status(
        selected_date="2026-03-24",
        raw_tickers_dir=raw_dir,
        runs_root=tmp_path / "runs",
    )
    assert out["status"] == "RED"
    assert out["index_code"] == "IDX_DATA_MISSING"


def test_compute_round_status_green_when_data_present_without_run(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw" / "tickers"
    _seed_all_tickers(raw_dir)

    out = compute_round_status(
        selected_date="2026-03-24",
        raw_tickers_dir=raw_dir,
        runs_root=tmp_path / "runs",
    )
    assert out["status"] == "GREEN"
    assert out["index_code"] == "IDX_CALC_PENDING"


def test_compute_round_status_green_when_successful_run_but_violet_missing(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw" / "tickers"
    _seed_all_tickers(raw_dir)
    runs_root = tmp_path / "runs"

    run = create_run(
        selected_date="2026-03-24",
        selected_ticker="ALL",
        total_stages=18,
        root_dir=runs_root,
    )
    idx = 1
    for ticker in ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"):
        for stage_name in ("svl_export", "tda_export", "make_fh3_table"):
            append_stage_result(
                run_id=str(run["run_id"]),
                stage_index=idx,
                stage_name=stage_name,
                category="core",
                ticker=ticker,
                command=["python", stage_name],
                returncode=0,
                stdout="ok",
                stderr="",
                duration_seconds=0.1,
                root_dir=runs_root,
            )
            idx += 1
    finalize_run(str(run["run_id"]), root_dir=runs_root)

    out = compute_round_status(
        selected_date="2026-03-24",
        raw_tickers_dir=raw_dir,
        runs_root=runs_root,
    )
    assert out["status"] == "GREEN"
    assert out["index_code"] == "IDX_VIOLET_MISSING"


def test_compute_round_status_accepts_global_fh3_stage(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "tickers"
    _seed_all_tickers(raw_dir)
    runs_root = tmp_path / "runs"

    run = create_run(
        selected_date="2026-03-24",
        selected_ticker="ALL",
        total_stages=13,
        root_dir=runs_root,
    )
    idx = 1
    for ticker in ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"):
        for stage_name in ("svl_export", "tda_export"):
            append_stage_result(
                run_id=str(run["run_id"]),
                stage_index=idx,
                stage_name=stage_name,
                category="core",
                ticker=ticker,
                command=["python", stage_name],
                returncode=0,
                stdout="ok",
                stderr="",
                duration_seconds=0.1,
                root_dir=runs_root,
            )
            idx += 1
    append_stage_result(
        run_id=str(run["run_id"]),
        stage_index=idx,
        stage_name="make_fh3_table",
        category="core",
        ticker="ALL",
        command=[
            "python",
            "make_fh3_table",
            "--tickers",
            "TNX",
            "DJI",
            "SPX",
            "VIX",
            "QQQ",
            "AAPL",
        ],
        returncode=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.1,
        root_dir=runs_root,
    )
    finalize_run(str(run["run_id"]), root_dir=runs_root)

    out = compute_round_status(
        selected_date="2026-03-24",
        raw_tickers_dir=raw_dir,
        runs_root=runs_root,
    )
    assert out["status"] == "GREEN"
    assert out["index_code"] == "IDX_VIOLET_MISSING"


def test_compute_round_status_blue_when_violet_scores_exist(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "tickers"
    _seed_all_tickers(raw_dir)
    runs_root = tmp_path / "runs"
    vg_db_path = tmp_path / "out" / "i_calc" / "ML" / "ML_VG_tables.sqlite"
    _seed_violet_score(vg_db_path, "2026-03-24")

    run = create_run(
        selected_date="2026-03-24",
        selected_ticker="ALL",
        total_stages=18,
        root_dir=runs_root,
    )
    idx = 1
    for ticker in ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"):
        for stage_name in ("svl_export", "tda_export", "make_fh3_table"):
            append_stage_result(
                run_id=str(run["run_id"]),
                stage_index=idx,
                stage_name=stage_name,
                category="core",
                ticker=ticker,
                command=["python", stage_name],
                returncode=0,
                stdout="ok",
                stderr="",
                duration_seconds=0.1,
                root_dir=runs_root,
            )
            idx += 1
    finalize_run(str(run["run_id"]), root_dir=runs_root)

    out = compute_round_status(
        selected_date="2026-03-24",
        raw_tickers_dir=raw_dir,
        runs_root=runs_root,
        vg_db_path=vg_db_path,
    )
    assert out["status"] == "BLUE"
    assert out["index_code"] == "IDX_CALC_COMPLETE"


def test_compute_round_status_violet_when_failed_run_exists(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "tickers"
    _seed_all_tickers(raw_dir)
    runs_root = tmp_path / "runs"

    run = create_run(
        selected_date="2026-03-24",
        selected_ticker="TNX",
        total_stages=1,
        root_dir=runs_root,
    )
    stage = append_stage_result(
        run_id=str(run["run_id"]),
        stage_index=1,
        stage_name="svl_export",
        category="core",
        ticker="TNX",
        command=["python", "scripts/svl_export.py"],
        returncode=1,
        stdout="",
        stderr="failure",
        duration_seconds=0.2,
        root_dir=runs_root,
    )
    finalize_run(str(run["run_id"]), root_dir=runs_root)

    out = compute_round_status(
        selected_date="2026-03-24",
        raw_tickers_dir=raw_dir,
        runs_root=runs_root,
    )
    assert out["status"] == "VIOLET"
    assert out["index_code"] == "IDX_CALC_ERROR"
    assert out["log_id"] == stage["log_id"]


def test_compute_round_status_accepts_month_name_dates(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw" / "tickers"
    for ticker in ("TNX", "DJI", "GSPC", "VIX", "QQQ", "AAPL"):
        _write_ticker_csv(
            raw_dir / f"{ticker}_data.csv",
            [("Mar 31, 2026", 1.0), ("Mar 24, 2026", 0.9)],
        )

    out = compute_round_status(
        selected_date="2026-03-31",
        raw_tickers_dir=raw_dir,
        runs_root=tmp_path / "runs",
    )
    assert out["status"] == "GREEN"
    assert out["missing_tickers"] == []
