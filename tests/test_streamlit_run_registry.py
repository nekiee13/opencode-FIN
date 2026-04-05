from __future__ import annotations

from pathlib import Path

from src.ui.services.run_registry import (
    append_stage_result,
    create_run,
    finalize_run,
    latest_run_for_date,
    list_runs,
    load_run,
)


def test_run_registry_persists_and_loads(tmp_path: Path) -> None:
    run = create_run(
        selected_date="2026-03-24",
        selected_ticker="ALL",
        total_stages=2,
        root_dir=tmp_path,
    )
    run_id = str(run["run_id"])

    stage = append_stage_result(
        run_id=run_id,
        stage_index=1,
        stage_name="svl_export",
        category="core",
        ticker="TNX",
        command=["python", "scripts/svl_export.py"],
        returncode=0,
        stdout="ok",
        stderr="",
        duration_seconds=1.25,
        root_dir=tmp_path,
    )
    assert stage["status"] == "success"
    assert stage["log_id"].startswith(run_id)

    finished = finalize_run(run_id=run_id, root_dir=tmp_path)
    assert finished["status"] == "success"

    loaded = load_run(run_id=run_id, root_dir=tmp_path)
    assert loaded is not None
    assert loaded["completed_stages"] == 1
    assert loaded["failed_stages"] == 0


def test_latest_run_for_date_prefers_newest(tmp_path: Path) -> None:
    run_a = create_run(
        selected_date="2026-03-24",
        selected_ticker="ALL",
        total_stages=1,
        root_dir=tmp_path,
    )
    finalize_run(str(run_a["run_id"]), root_dir=tmp_path)

    run_b = create_run(
        selected_date="2026-03-24",
        selected_ticker="TNX",
        total_stages=1,
        root_dir=tmp_path,
    )
    append_stage_result(
        run_id=str(run_b["run_id"]),
        stage_index=1,
        stage_name="svl_export",
        category="core",
        ticker="TNX",
        command=["python", "scripts/svl_export.py"],
        returncode=1,
        stdout="",
        stderr="failure",
        duration_seconds=0.4,
        root_dir=tmp_path,
    )
    finalize_run(str(run_b["run_id"]), root_dir=tmp_path)

    latest = latest_run_for_date("2026-03-24", root_dir=tmp_path)
    assert latest is not None
    assert latest["run_id"] == run_b["run_id"]
    assert latest["status"] == "failed"

    runs = list_runs(root_dir=tmp_path)
    assert len(runs) == 2
