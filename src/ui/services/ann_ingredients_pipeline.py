from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from src.config import paths
from src.ui.services.batch_chain import select_processing_dates
from src.ui.services.date_sources import load_sidebar_date_options
from src.ui.services.pipeline_runner import CommandSpec, TICKER_ORDER, run_command


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalize_ticker_list(tickers: Sequence[str] | None = None) -> list[str]:
    if tickers is None:
        return [str(x) for x in TICKER_ORDER]
    out: list[str] = []
    for raw in tickers:
        text = str(raw or "").strip().upper().replace("^", "")
        if text == "GSPC":
            text = "SPX"
        if text and text not in out:
            out.append(text)
    return out


def resolve_processing_dates(
    *,
    start_date: str,
    end_date: str | None,
    explicit_dates: Sequence[str] | None,
) -> list[str]:
    if explicit_dates:
        available = [str(x) for x in explicit_dates]
    else:
        available = load_sidebar_date_options()
    return select_processing_dates(
        available_dates=available,
        start_date=str(start_date),
        end_date=str(end_date or "").strip() or None,
    )


def build_ann_ingredient_commands(
    *,
    selected_date: str,
    tickers: Sequence[str],
    python_exec: str = "python",
    ingest_after_each_date: bool,
) -> list[CommandSpec]:
    repo_root = paths.APP_ROOT
    scripts_dir = repo_root / "scripts"
    tickers_list = normalize_ticker_list(tickers)
    replay = ["--history-mode", "replay", "--as-of-date", str(selected_date)]
    commands: list[CommandSpec] = [
        CommandSpec(
            category="ingredients",
            stage="ti_pp_backfill",
            ticker="ALL",
            cwd=repo_root,
            command=[
                str(python_exec),
                str(scripts_dir / "ti_pp_backfill.py"),
                "--selected-date",
                str(selected_date),
                "--tickers",
                *tickers_list,
                "--stop-on-error",
            ],
        ),
        CommandSpec(
            category="ingredients",
            stage="svl_export",
            ticker="ALL",
            cwd=repo_root,
            command=[
                str(python_exec),
                str(scripts_dir / "svl_export.py"),
                "--csv-dir",
                str(paths.DATA_TICKERS_DIR),
                "--csv-suffix",
                "_data.csv",
                "--tickers",
                *tickers_list,
                "--map-json",
                json.dumps({"SPX": "GSPC"}),
                "--basename",
                "SVL",
                "--write-metrics",
                *replay,
            ],
        ),
        CommandSpec(
            category="ingredients",
            stage="tda_export",
            ticker="ALL",
            cwd=repo_root,
            command=[
                str(python_exec),
                str(scripts_dir / "tda_export.py"),
                "--raw-dir",
                str(paths.DATA_TICKERS_DIR),
                "--tickers",
                *tickers_list,
                "--map",
                "SPX=GSPC",
                "--write-metrics",
                "--write-prompt-header",
                *replay,
            ],
        ),
        CommandSpec(
            category="ingredients",
            stage="make_fh3_table",
            ticker="ALL",
            cwd=repo_root,
            command=[
                str(python_exec),
                str(scripts_dir / "make_fh3_table.py"),
                "--tickers",
                *tickers_list,
                *replay,
            ],
        ),
    ]

    if ingest_after_each_date:
        commands.append(
            CommandSpec(
                category="ingredients",
                stage="ann_feature_ingest",
                ticker="ALL",
                cwd=repo_root,
                command=[
                    str(python_exec),
                    str(scripts_dir / "ann_feature_stores_ingest.py"),
                ],
            )
        )

    return commands


def run_ann_ingredients_for_dates(
    *,
    dates: Sequence[str],
    tickers: Sequence[str],
    python_exec: str,
    ingest_after_each_date: bool,
    stop_on_error: bool,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    tickers_list = normalize_ticker_list(tickers)
    run_results: list[dict[str, Any]] = []

    def _emit(payload: dict[str, Any]) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(dict(payload))
        except Exception:
            return

    any_failed = False
    failed_date = ""
    failed_stage = ""

    for date_text in list(dates):
        commands = build_ann_ingredient_commands(
            selected_date=str(date_text),
            tickers=tickers_list,
            python_exec=str(python_exec),
            ingest_after_each_date=bool(ingest_after_each_date),
        )
        stage_rows: list[dict[str, Any]] = []
        date_failed = False
        for spec in commands:
            _emit(
                {
                    "event": "stage_start",
                    "selected_date": str(date_text),
                    "stage": str(spec.stage),
                }
            )
            result = run_command(spec)
            stage_row = {
                "stage": str(spec.stage),
                "ticker": str(spec.ticker or "ALL"),
                "command": [str(x) for x in list(spec.command)],
                "returncode": int(result.returncode),
                "duration_seconds": float(result.duration_seconds),
                "stdout": str(result.stdout),
                "stderr": str(result.stderr),
            }
            stage_rows.append(stage_row)
            _emit(
                {
                    "event": "stage_done",
                    "selected_date": str(date_text),
                    "stage": str(spec.stage),
                    "returncode": int(result.returncode),
                    "duration_seconds": float(result.duration_seconds),
                    "stdout": str(result.stdout),
                    "stderr": str(result.stderr),
                }
            )
            if int(result.returncode) != 0:
                date_failed = True
                any_failed = True
                failed_date = str(date_text)
                failed_stage = str(spec.stage)
                break

        date_status = "failed" if date_failed else "success"
        run_results.append(
            {
                "selected_date": str(date_text),
                "status": date_status,
                "stages": stage_rows,
            }
        )
        _emit(
            {
                "event": "date_done",
                "selected_date": str(date_text),
                "status": date_status,
            }
        )

        if date_failed and stop_on_error:
            break

    end_ingest: dict[str, Any] | None = None
    if (not ingest_after_each_date) and (not any_failed):
        spec = CommandSpec(
            category="ingredients",
            stage="ann_feature_ingest_end",
            ticker="ALL",
            cwd=paths.APP_ROOT,
            command=[
                str(python_exec),
                str(paths.APP_ROOT / "scripts" / "ann_feature_stores_ingest.py"),
            ],
        )
        _emit(
            {
                "event": "stage_start",
                "selected_date": "ALL_DATES",
                "stage": str(spec.stage),
            }
        )
        result = run_command(spec)
        end_ingest = {
            "stage": str(spec.stage),
            "command": [str(x) for x in list(spec.command)],
            "returncode": int(result.returncode),
            "duration_seconds": float(result.duration_seconds),
            "stdout": str(result.stdout),
            "stderr": str(result.stderr),
        }
        _emit(
            {
                "event": "stage_done",
                "selected_date": "ALL_DATES",
                "stage": str(spec.stage),
                "returncode": int(result.returncode),
                "duration_seconds": float(result.duration_seconds),
                "stdout": str(result.stdout),
                "stderr": str(result.stderr),
            }
        )
        if int(result.returncode) != 0:
            any_failed = True
            failed_date = "ALL_DATES"
            failed_stage = str(spec.stage)

    success_count = sum(
        1 for item in run_results if str(item.get("status") or "") == "success"
    )
    failed_count = len(run_results) - success_count
    ended = datetime.now(timezone.utc)

    return {
        "status": "success" if not any_failed else "failed",
        "generated_at": _utc_now_iso(),
        "started_at": started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ended_at": ended.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dates_requested": [str(x) for x in list(dates)],
        "tickers": tickers_list,
        "ingest_after_each_date": bool(ingest_after_each_date),
        "results": run_results,
        "success_count": int(success_count),
        "failed_count": int(failed_count),
        "failed_date": failed_date,
        "failed_stage": failed_stage,
        "end_ingest": end_ingest,
    }


def write_run_summary(*, summary: dict[str, Any], log_dir: Path | None = None) -> Path:
    out_dir = (log_dir or (paths.OUT_I_CALC_DIR / "gui_ops" / "batch")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"ann_ingredients_backfill_{stamp}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


__all__ = [
    "normalize_ticker_list",
    "resolve_processing_dates",
    "build_ann_ingredient_commands",
    "run_ann_ingredients_for_dates",
    "write_run_summary",
]
