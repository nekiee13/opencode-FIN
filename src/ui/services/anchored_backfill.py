from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from src.config import paths

_FORECAST_RE = re.compile(r"forecast_date\s*=\s*(\d{4}-\d{2}-\d{2})")


def _derive_round_id(selected_date: str) -> str:
    text = str(selected_date or "").strip()
    compact = re.sub(r"[^0-9]", "", text)
    if len(compact) == 8:
        return f"anchor-{compact}"
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", text).strip("-")
    if not safe:
        return "anchor-date"
    return f"anchor-{safe}"


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    elapsed = float(time.monotonic() - started)
    return {
        "command": [str(x) for x in command],
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
        "duration_seconds": elapsed,
    }


def _extract_forecast_date(text: str) -> str:
    m = _FORECAST_RE.search(str(text or ""))
    if m:
        return str(m.group(1))
    return ""


def run_anchored_backfill(
    *,
    selected_date: str,
    selected_ticker: str | None = None,
    repo_root: Path | None = None,
    python_exec: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    _ = selected_ticker
    date_text = str(selected_date or "").strip()
    if not date_text:
        return {
            "status": "error",
            "index_code": "BACKFILL_SELECTED_DATE_MISSING",
            "summary": "Selected date is required.",
            "stages": [],
        }

    root = (repo_root or paths.APP_ROOT).resolve()
    scripts = root / "scripts"
    py = str(python_exec or sys.executable)
    round_id = _derive_round_id(date_text)
    stage_results: list[dict[str, Any]] = []

    draft_cmd = [
        py,
        str(scripts / "followup_ml.py"),
        "draft",
        "--round-id",
        round_id,
        "--fh",
        "1",
        "--history-mode",
        "replay",
        "--as-of-date",
        date_text,
    ]
    finalize_cmd = [
        py,
        str(scripts / "followup_ml.py"),
        "finalize",
        "--round-id",
        round_id,
    ]
    ingest_cmd = [
        py,
        str(scripts / "followup_ml_vg.py"),
        "ingest-round",
        "--round-id",
        round_id,
    ]

    total_steps = 4

    def _emit(step: int, stage: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(int(step), int(total_steps), str(stage))
        except Exception:
            return

    for name, cmd in (
        ("draft", draft_cmd),
        ("finalize", finalize_cmd),
        ("ingest", ingest_cmd),
    ):
        _emit(len(stage_results), name)
        out = _run_command(cmd, cwd=root)
        out["stage"] = name
        stage_results.append(out)
        if int(out["returncode"]) != 0:
            return {
                "status": "error",
                "index_code": f"BACKFILL_{name.upper()}_FAILED",
                "summary": f"Anchored backfill failed at stage: {name}.",
                "selected_date": date_text,
                "round_id": round_id,
                "stages": stage_results,
            }

    forecast_date = _extract_forecast_date(
        str(stage_results[-1].get("stdout") or "")
        + "\n"
        + str(stage_results[-1].get("stderr") or "")
    )
    if not forecast_date:
        return {
            "status": "error",
            "index_code": "BACKFILL_FORECAST_DATE_MISSING",
            "summary": "Ingest completed but forecast_date could not be parsed from output.",
            "selected_date": date_text,
            "round_id": round_id,
            "stages": stage_results,
        }

    materialize_cmd = [
        py,
        str(scripts / "followup_ml_vg.py"),
        "materialize",
        "--forecast-date",
        forecast_date,
        "--memory-tail",
        "4",
        "--bootstrap-enabled",
        "--bootstrap-score",
        "99.0",
    ]
    _emit(3, "materialize")
    materialize_out = _run_command(materialize_cmd, cwd=root)
    materialize_out["stage"] = "materialize"
    stage_results.append(materialize_out)
    if int(materialize_out["returncode"]) != 0:
        return {
            "status": "error",
            "index_code": "BACKFILL_MATERIALIZE_FAILED",
            "summary": "Anchored backfill failed at stage: materialize.",
            "selected_date": date_text,
            "round_id": round_id,
            "forecast_date": forecast_date,
            "stages": stage_results,
        }

    _emit(4, "done")

    return {
        "status": "success",
        "index_code": "BACKFILL_OK",
        "summary": "Anchored backfill completed.",
        "selected_date": date_text,
        "round_id": round_id,
        "forecast_date": forecast_date,
        "stages": stage_results,
    }
