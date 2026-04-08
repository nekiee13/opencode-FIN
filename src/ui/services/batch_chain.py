from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Any, Callable

from src.config import paths
from src.ui.services.anchored_backfill import run_anchored_backfill
from src.ui.services.date_sources import load_sidebar_date_options
from src.ui.services.pipeline_qa import evaluate_pipeline_state, write_pipeline_qa_log
from src.ui.services.pipeline_runner import build_pipeline_commands, run_command
from src.ui.services.run_registry import append_stage_result, create_run, finalize_run
from src.ui.services.vg_loader import materialize_for_selected_date


def _parse_iso_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def select_processing_dates(
    *,
    available_dates: list[str],
    start_date: str,
    end_date: str | None = None,
) -> list[str]:
    start_dt = _parse_iso_date(start_date)
    if start_dt is None:
        raise ValueError(f"Invalid start_date: {start_date!r}")
    end_dt = _parse_iso_date(str(end_date or "").strip()) if end_date else None

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in available_dates:
        text = str(raw or "").strip()
        dt = _parse_iso_date(text)
        if dt is None:
            continue
        if dt < start_dt:
            continue
        if end_dt is not None and dt > end_dt:
            continue
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    normalized.sort()
    return normalized


@dataclass(frozen=True)
class StageLog:
    stage: str
    returncode: int
    duration_seconds: float


def _emit_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    payload: dict[str, Any],
) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(dict(payload))
    except Exception:
        return


def run_full_chain_for_date(
    *,
    selected_date: str,
    selected_ticker: str = "ALL",
    python_exec: str | None = None,
    run_load_blue_green: bool = True,
    runs_root: Path | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    selected_text = str(selected_date or "").strip()
    out: dict[str, Any] = {
        "selected_date": selected_text,
        "selected_ticker": str(selected_ticker or "ALL"),
        "pipeline_ok": False,
        "backfill_ok": False,
        "load_blue_green_ok": False,
        "qa_index_code": "",
        "overall_status": "unknown",
        "pipeline_stages": [],
    }

    specs = build_pipeline_commands(
        selected_date=selected_text,
        selected_ticker=str(selected_ticker or "ALL"),
        python_exec=python_exec,
    )

    run_id = ""
    try:
        run_payload = create_run(
            selected_date=selected_text,
            selected_ticker=str(selected_ticker or "ALL"),
            total_stages=len(specs),
            root_dir=runs_root,
        )
        run_id = str(run_payload.get("run_id") or "")
    except Exception as exc:
        out["run_registry_error"] = str(exc)
    if run_id:
        out["run_id"] = run_id

    stage_logs: list[dict[str, Any]] = []
    for spec in specs:
        stage_index = len(stage_logs) + 1
        _emit_progress(
            progress_callback,
            {
                "event": "pipeline_stage_start",
                "selected_date": selected_text,
                "run_id": run_id,
                "stage_index": stage_index,
                "stage_total": len(specs),
                "stage": str(spec.stage),
                "ticker": spec.ticker,
            },
        )
        result = run_command(spec)
        stage_payload = {
            "stage": str(spec.stage),
            "category": str(spec.category),
            "ticker": spec.ticker,
            "returncode": int(result.returncode),
            "duration_seconds": float(result.duration_seconds),
        }
        stage_logs.append(stage_payload)
        if run_id:
            command_value = getattr(spec, "command", None)
            if isinstance(command_value, list):
                command = [str(x) for x in command_value]
            else:
                command = [str(spec.stage)]
            append_stage_result(
                run_id=run_id,
                stage_index=stage_index,
                stage_name=spec.stage,
                category=spec.category,
                ticker=spec.ticker,
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=round(float(result.duration_seconds), 3),
                root_dir=runs_root,
            )
        _emit_progress(
            progress_callback,
            {
                "event": "pipeline_stage_done",
                "selected_date": selected_text,
                "run_id": run_id,
                "stage_index": stage_index,
                "stage_total": len(specs),
                "stage": str(spec.stage),
                "ticker": spec.ticker,
                "returncode": int(result.returncode),
                "status": "success" if int(result.returncode) == 0 else "failed",
            },
        )
        if int(result.returncode) != 0:
            if run_id:
                finished = finalize_run(run_id, root_dir=runs_root)
                out["run_status"] = str(finished.get("status") or "")
            out["pipeline_stages"] = stage_logs
            out["overall_status"] = "pipeline_failed"
            return out

    out["pipeline_ok"] = True
    out["pipeline_stages"] = stage_logs
    if run_id:
        finished = finalize_run(run_id, root_dir=runs_root)
        out["run_status"] = str(finished.get("status") or "")

    _emit_progress(
        progress_callback,
        {
            "event": "backfill_start",
            "selected_date": selected_text,
            "run_id": run_id,
        },
    )
    backfill = run_anchored_backfill(
        selected_date=selected_text,
        selected_ticker=str(selected_ticker or "ALL"),
        python_exec=python_exec,
    )
    out["backfill"] = backfill
    out["backfill_ok"] = str(backfill.get("status") or "") == "success"
    _emit_progress(
        progress_callback,
        {
            "event": "backfill_done",
            "selected_date": selected_text,
            "run_id": run_id,
            "status": "success" if out["backfill_ok"] else "failed",
            "index_code": str(backfill.get("index_code") or ""),
        },
    )
    if not out["backfill_ok"]:
        out["overall_status"] = "backfill_failed"
        return out

    if run_load_blue_green:
        _emit_progress(
            progress_callback,
            {
                "event": "load_blue_green_start",
                "selected_date": selected_text,
                "run_id": run_id,
            },
        )
        try:
            load_result = materialize_for_selected_date(
                selected_date=selected_text,
                memory_tail=4,
                bootstrap_enabled=True,
                policy_name="value_assign_v1",
                fh3_dir=paths.OUT_I_CALC_FH3_DIR,
            )
            out["load_blue_green_result"] = load_result
            out["load_blue_green_ok"] = True
            _emit_progress(
                progress_callback,
                {
                    "event": "load_blue_green_done",
                    "selected_date": selected_text,
                    "run_id": run_id,
                    "status": "success",
                },
            )
        except Exception as exc:
            out["load_blue_green_ok"] = False
            out["load_blue_green_error"] = str(exc)
            out["overall_status"] = "load_blue_green_failed"
            _emit_progress(
                progress_callback,
                {
                    "event": "load_blue_green_done",
                    "selected_date": selected_text,
                    "run_id": run_id,
                    "status": "failed",
                    "error": str(exc),
                },
            )
            return out
    else:
        out["load_blue_green_ok"] = True

    _emit_progress(
        progress_callback,
        {
            "event": "qa_start",
            "selected_date": selected_text,
            "run_id": run_id,
        },
    )
    qa_report = evaluate_pipeline_state(
        selected_date=selected_text, runs_root=runs_root
    )
    qa_log_path = write_pipeline_qa_log(report=qa_report)
    out["qa_index_code"] = str(qa_report.get("index_code") or "")
    out["qa_log_path"] = str(qa_log_path)
    out["qa_report"] = qa_report
    out["overall_status"] = (
        "success" if out["qa_index_code"] == "QA_OK" else "qa_not_ok"
    )
    _emit_progress(
        progress_callback,
        {
            "event": "qa_done",
            "selected_date": selected_text,
            "run_id": run_id,
            "qa_index_code": out["qa_index_code"],
            "status": "success" if out["overall_status"] == "success" else "failed",
        },
    )
    return out


def run_full_chain_for_dates(
    *,
    dates: list[str],
    selected_ticker: str = "ALL",
    python_exec: str | None = None,
    run_load_blue_green: bool = True,
    stop_on_error: bool = False,
    runs_root: Path | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    started_at = time.perf_counter()
    total = len(dates)
    for date_value in dates:
        index = len(results) + 1
        item = run_full_chain_for_date(
            selected_date=str(date_value),
            selected_ticker=selected_ticker,
            python_exec=python_exec,
            run_load_blue_green=run_load_blue_green,
            runs_root=runs_root,
            progress_callback=progress_callback,
        )
        results.append(item)
        elapsed = float(time.perf_counter() - started_at)
        completed = len(results)
        avg_seconds = elapsed / float(max(completed, 1))
        eta_seconds = avg_seconds * float(max(total - completed, 0))
        success_count_so_far = sum(
            1 for x in results if str(x.get("overall_status") or "") == "success"
        )
        _emit_progress(
            progress_callback,
            {
                "event": "date_complete",
                "index": index,
                "total": total,
                "selected_date": str(date_value),
                "overall_status": str(item.get("overall_status") or "unknown"),
                "success_count": int(success_count_so_far),
                "failed_count": int(completed - success_count_so_far),
                "elapsed_seconds": round(elapsed, 3),
                "eta_seconds": round(eta_seconds, 3),
            },
        )
        if stop_on_error and str(item.get("overall_status") or "") != "success":
            break

    success_count = sum(1 for x in results if str(x.get("overall_status")) == "success")
    failed_count = len(results) - success_count
    return {
        "dates_requested": list(dates),
        "results": results,
        "success_count": int(success_count),
        "failed_count": int(failed_count),
    }


def load_dates_for_batch(*, start_date: str, end_date: str | None = None) -> list[str]:
    available = load_sidebar_date_options()
    return select_processing_dates(
        available_dates=available,
        start_date=start_date,
        end_date=end_date,
    )
