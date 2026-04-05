from __future__ import annotations

import csv
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


def test_compute_round_status_blue_when_successful_run_exists(tmp_path: Path) -> None:
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
    assert out["status"] == "BLUE"


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
    assert out["log_id"] == stage["log_id"]
