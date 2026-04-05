from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.config import paths
from src.ui.services.error_parse import classify_stage_error


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _root(root_dir: Path | None = None) -> Path:
    return (root_dir or (paths.OUT_I_CALC_DIR / "gui_ops")).resolve()


def _runs_dir(root_dir: Path | None = None) -> Path:
    out = _root(root_dir) / "runs"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _logs_dir(run_id: str, root_dir: Path | None = None) -> Path:
    out = _root(root_dir) / "logs" / str(run_id)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _run_file(run_id: str, root_dir: Path | None = None) -> Path:
    return _runs_dir(root_dir) / f"{run_id}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def create_run(
    *,
    selected_date: str,
    selected_ticker: str,
    total_stages: int,
    root_dir: Path | None = None,
) -> dict[str, Any]:
    run_id = (
        f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    )
    record: dict[str, Any] = {
        "run_id": run_id,
        "selected_date": str(selected_date),
        "selected_ticker": str(selected_ticker),
        "created_at": _now_iso(),
        "ended_at": None,
        "status": "running",
        "total_stages": int(total_stages),
        "completed_stages": 0,
        "failed_stages": 0,
        "stages": [],
    }
    _write_json(_run_file(run_id, root_dir), record)
    return record


def load_run(run_id: str, root_dir: Path | None = None) -> dict[str, Any] | None:
    path = _run_file(run_id, root_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def append_stage_result(
    *,
    run_id: str,
    stage_index: int,
    stage_name: str,
    category: str,
    ticker: str | None,
    command: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
    duration_seconds: float,
    root_dir: Path | None = None,
) -> dict[str, Any]:
    run = load_run(run_id, root_dir)
    if run is None:
        raise ValueError(f"run not found: {run_id}")

    log_id = f"{run_id}-{int(stage_index):02d}"
    ticker_tag = str(ticker or "ALL")
    log_path = (
        _logs_dir(run_id, root_dir)
        / f"{int(stage_index):02d}_{stage_name}_{ticker_tag}.log"
    )

    reason_code = classify_stage_error(
        returncode=int(returncode),
        stderr=str(stderr),
        stdout=str(stdout),
    )
    status = "success" if int(returncode) == 0 else "failed"

    log_lines = [
        f"run_id={run_id}",
        f"log_id={log_id}",
        f"stage_index={int(stage_index)}",
        f"stage={stage_name}",
        f"category={category}",
        f"ticker={ticker_tag}",
        f"returncode={int(returncode)}",
        f"reason_code={reason_code}",
        f"duration_seconds={float(duration_seconds):.3f}",
        f"recorded_at={_now_iso()}",
        "command=" + " ".join(command),
        "--- STDOUT ---",
        str(stdout),
        "--- STDERR ---",
        str(stderr),
    ]
    log_path.write_text("\n".join(log_lines), encoding="utf-8")

    stage_record = {
        "index": int(stage_index),
        "stage": str(stage_name),
        "category": str(category),
        "ticker": ticker,
        "command": list(command),
        "status": status,
        "returncode": int(returncode),
        "reason_code": reason_code,
        "duration_seconds": float(duration_seconds),
        "log_id": log_id,
        "log_path": str(log_path),
        "stdout": str(stdout),
        "stderr": str(stderr),
        "recorded_at": _now_iso(),
    }
    stages = list(run.get("stages", []))
    stages.append(stage_record)
    run["stages"] = stages
    run["completed_stages"] = int(run.get("completed_stages", 0)) + 1
    if status == "failed":
        run["failed_stages"] = int(run.get("failed_stages", 0)) + 1

    _write_json(_run_file(run_id, root_dir), run)
    return stage_record


def finalize_run(run_id: str, root_dir: Path | None = None) -> dict[str, Any]:
    run = load_run(run_id, root_dir)
    if run is None:
        raise ValueError(f"run not found: {run_id}")
    failed = int(run.get("failed_stages", 0))
    run["status"] = "failed" if failed > 0 else "success"
    run["ended_at"] = _now_iso()
    _write_json(_run_file(run_id, root_dir), run)
    return run


def list_runs(
    *,
    limit: int = 20,
    selected_date: str | None = None,
    root_dir: Path | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in _runs_dir(root_dir).glob("RUN-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if selected_date and str(payload.get("selected_date", "")) != str(
            selected_date
        ):
            continue
        out.append(payload)

    out.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return out[: int(limit)]


def latest_run_for_date(
    selected_date: str,
    *,
    root_dir: Path | None = None,
) -> dict[str, Any] | None:
    runs = list_runs(limit=50, selected_date=selected_date, root_dir=root_dir)
    if not runs:
        return None
    return runs[0]
