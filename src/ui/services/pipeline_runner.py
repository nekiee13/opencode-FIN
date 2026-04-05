from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from src.config import paths

TICKER_ORDER: tuple[str, ...] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")


@dataclass(frozen=True)
class CommandSpec:
    category: str
    stage: str
    ticker: str | None
    command: list[str]
    cwd: Path


@dataclass(frozen=True)
class CommandResult:
    spec: CommandSpec
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


def _replay_args(selected_date: str) -> list[str]:
    date_value = str(selected_date or "").strip()
    if not date_value:
        return []
    return ["--history-mode", "replay", "--as-of-date", date_value]


def _selected_tickers(selected_ticker: str) -> list[str]:
    value = str(selected_ticker or "").strip().upper()
    if value in {"", "ALL", "ALL_TICKERS"}:
        return list(TICKER_ORDER)
    return [value]


def build_pipeline_commands(
    *,
    selected_date: str,
    selected_ticker: str,
    python_exec: str | None = None,
) -> list[CommandSpec]:
    py = python_exec or sys.executable
    repo_root = paths.APP_ROOT
    scripts_dir = repo_root / "scripts"
    replay = _replay_args(selected_date)
    commands: list[CommandSpec] = []

    for ticker in _selected_tickers(selected_ticker):
        commands.append(
            CommandSpec(
                category="core",
                stage="svl_export",
                ticker=ticker,
                cwd=repo_root,
                command=[
                    py,
                    str(scripts_dir / "svl_export.py"),
                    "--csv-dir",
                    str(paths.DATA_TICKERS_DIR),
                    "--csv-suffix",
                    "_data.csv",
                    "--tickers",
                    ticker,
                    "--map-json",
                    json.dumps({"SPX": "GSPC"}),
                    "--basename",
                    "SVL",
                    "--write-metrics",
                    "--print",
                    *replay,
                ],
            )
        )
        commands.append(
            CommandSpec(
                category="core",
                stage="tda_export",
                ticker=ticker,
                cwd=repo_root,
                command=[
                    py,
                    str(scripts_dir / "tda_export.py"),
                    "--raw-dir",
                    str(paths.DATA_TICKERS_DIR),
                    "--tickers",
                    ticker,
                    "--map",
                    "SPX=GSPC",
                    "--write-metrics",
                    "--write-prompt-header",
                    *replay,
                ],
            )
        )
        commands.append(
            CommandSpec(
                category="core",
                stage="make_fh3_table",
                ticker=ticker,
                cwd=repo_root,
                command=[
                    py,
                    str(scripts_dir / "make_fh3_table.py"),
                    "--tickers",
                    ticker,
                    *replay,
                ],
            )
        )

    commands.append(
        CommandSpec(
            category="store",
            stage="vg_init",
            ticker=None,
            cwd=repo_root,
            command=[py, str(scripts_dir / "followup_ml_vg.py"), "init-db"],
        )
    )
    commands.append(
        CommandSpec(
            category="store",
            stage="ann_ingest",
            ticker=None,
            cwd=repo_root,
            command=[py, str(scripts_dir / "ann_markers_ingest.py")],
        )
    )
    return commands


def run_command(spec: CommandSpec) -> CommandResult:
    start = time.monotonic()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run(
        spec.command,
        cwd=str(spec.cwd),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    elapsed = time.monotonic() - start
    return CommandResult(
        spec=spec,
        returncode=int(proc.returncode),
        stdout=str(proc.stdout),
        stderr=str(proc.stderr),
        duration_seconds=float(elapsed),
    )
