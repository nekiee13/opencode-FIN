from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from src.config import paths
from src.ui.services.ann_feature_store import load_ann_feature_store_summary


def load_ann_store_summary(store_path: Path) -> dict[str, Any]:
    return load_ann_feature_store_summary(store_path)


def run_ann_feature_stores_ingest(
    *,
    python_exec: str | None = None,
    ti_dir: Path | None = None,
    pp_dir: Path | None = None,
    svl_dir: Path | None = None,
    tda_dir: Path | None = None,
    store_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    py = python_exec or sys.executable
    scripts_dir = paths.APP_ROOT / "scripts"
    cmd = [py, str(scripts_dir / "ann_feature_stores_ingest.py")]
    if ti_dir is not None:
        cmd.extend(["--ti-dir", str(ti_dir)])
    if pp_dir is not None:
        cmd.extend(["--pp-dir", str(pp_dir)])
    if svl_dir is not None:
        cmd.extend(["--svl-dir", str(svl_dir)])
    if tda_dir is not None:
        cmd.extend(["--tda-dir", str(tda_dir)])
    if store_path is not None:
        cmd.extend(["--store-path", str(store_path)])
    if force:
        cmd.append("--force")

    proc = subprocess.run(
        cmd,
        cwd=str(paths.APP_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout),
        "stderr": str(proc.stderr),
    }


def run_ann_markers_ingest(
    *,
    python_exec: str | None = None,
    raw_dir: Path | None = None,
    store_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    py = python_exec or sys.executable
    scripts_dir = paths.APP_ROOT / "scripts"
    cmd = [py, str(scripts_dir / "ann_markers_ingest.py")]
    if raw_dir is not None:
        cmd.extend(["--raw-dir", str(raw_dir)])
    if store_path is not None:
        cmd.extend(["--store-path", str(store_path)])
    if force:
        cmd.append("--force")

    proc = subprocess.run(
        cmd,
        cwd=str(paths.APP_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout),
        "stderr": str(proc.stderr),
    }


def run_ann_train(
    *,
    python_exec: str | None = None,
    tickers: list[str] | None = None,
    window_length: int | None = None,
    lag_depth: int | None = None,
) -> dict[str, Any]:
    py = python_exec or sys.executable
    scripts_dir = paths.APP_ROOT / "scripts"
    cmd = [py, str(scripts_dir / "ann_train.py")]
    if tickers:
        cmd.append("--tickers")
        cmd.extend([str(x).strip().upper() for x in tickers if str(x).strip()])
    if window_length is not None:
        cmd.extend(["--window-length", str(int(window_length))])
    if lag_depth is not None:
        cmd.extend(["--lag-depth", str(int(lag_depth))])

    proc = subprocess.run(
        cmd,
        cwd=str(paths.APP_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout),
        "stderr": str(proc.stderr),
    }


def run_ann_tune(
    *,
    python_exec: str | None = None,
    max_trials: int = 20,
) -> dict[str, Any]:
    py = python_exec or sys.executable
    scripts_dir = paths.APP_ROOT / "scripts"
    cmd = [py, str(scripts_dir / "ann_tune.py"), "--max-trials", str(int(max_trials))]

    proc = subprocess.run(
        cmd,
        cwd=str(paths.APP_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout),
        "stderr": str(proc.stderr),
    }
