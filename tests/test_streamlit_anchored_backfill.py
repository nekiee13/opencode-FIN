from __future__ import annotations

import subprocess
from pathlib import Path

from src.ui.services.anchored_backfill import run_anchored_backfill


class _Proc:
    def __init__(
        self, *, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> None:
        self.returncode = int(returncode)
        self.stdout = str(stdout)
        self.stderr = str(stderr)


def test_run_anchored_backfill_runs_replay_draft_then_ingest_materialize(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    scripts = repo_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append([str(x) for x in command])
        cmd = [str(x) for x in command]
        if "ingest-round" in cmd:
            return _Proc(
                stdout="\n".join(
                    [
                        "[followup-ml-vg] Round ingested",
                        "forecast_date=2025-07-30",
                        "rows_upserted=54",
                    ]
                )
                + "\n"
            )
        return _Proc(stdout="ok\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    out = run_anchored_backfill(
        selected_date="2025-07-29",
        repo_root=repo_root,
        python_exec="python-test",
    )

    assert out["status"] == "success"
    assert out["round_id"] == "anchor-20250729"
    assert out["forecast_date"] == "2025-07-30"
    assert len(calls) == 4

    assert calls[0] == [
        "python-test",
        str(scripts / "followup_ml.py"),
        "draft",
        "--round-id",
        "anchor-20250729",
        "--fh",
        "1",
        "--history-mode",
        "replay",
        "--as-of-date",
        "2025-07-29",
    ]
    assert calls[1] == [
        "python-test",
        str(scripts / "followup_ml.py"),
        "finalize",
        "--round-id",
        "anchor-20250729",
    ]
    assert calls[2] == [
        "python-test",
        str(scripts / "followup_ml_vg.py"),
        "ingest-round",
        "--round-id",
        "anchor-20250729",
    ]
    assert calls[3] == [
        "python-test",
        str(scripts / "followup_ml_vg.py"),
        "materialize",
        "--forecast-date",
        "2025-07-30",
        "--memory-tail",
        "4",
        "--bootstrap-enabled",
        "--bootstrap-score",
        "99.0",
    ]


def test_run_anchored_backfill_returns_error_when_ingest_forecast_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    scripts = repo_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)

    def fake_run(command, **kwargs):
        cmd = [str(x) for x in command]
        if "ingest-round" in cmd:
            return _Proc(stdout="[followup-ml-vg] Round ingested\n")
        return _Proc(stdout="ok\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    out = run_anchored_backfill(
        selected_date="2025-07-29",
        repo_root=repo_root,
        python_exec="python-test",
    )

    assert out["status"] == "error"
    assert out["index_code"] == "BACKFILL_FORECAST_DATE_MISSING"


def test_run_anchored_backfill_emits_progress_callback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    scripts = repo_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)

    events: list[tuple[int, int, str]] = []

    def fake_run(command, **kwargs):
        cmd = [str(x) for x in command]
        if "ingest-round" in cmd:
            return _Proc(stdout="forecast_date=2025-07-30\n")
        return _Proc(stdout="ok\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    out = run_anchored_backfill(
        selected_date="2025-07-29",
        repo_root=repo_root,
        python_exec="python-test",
        progress_callback=lambda step, total, stage: events.append(
            (step, total, stage)
        ),
    )

    assert out["status"] == "success"
    assert events == [
        (0, 4, "draft"),
        (1, 4, "finalize"),
        (2, 4, "ingest"),
        (3, 4, "materialize"),
        (4, 4, "done"),
    ]
