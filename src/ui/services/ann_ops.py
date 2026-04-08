from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.config import paths
from src.ui.services.ann_feature_store import load_ann_feature_store_summary


def extract_ann_train_run_dir(stdout: str) -> Path | None:
    for raw_line in str(stdout or "").splitlines():
        line = str(raw_line).strip()
        if not line.startswith("[ann_train] run_dir="):
            continue
        path_text = line.split("=", 1)[-1].strip()
        if not path_text:
            continue
        return Path(path_text)
    return None


def load_ann_train_artifacts(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    impacts_path = run_dir / "top_feature_impacts.json"
    out: dict[str, Any] = {
        "run_dir": str(run_dir),
        "summary": None,
        "top_feature_impacts": [],
    }
    if summary_path.exists():
        try:
            out["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            out["summary"] = None
    if impacts_path.exists():
        try:
            payload = json.loads(impacts_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                out["top_feature_impacts"] = payload
        except Exception:
            out["top_feature_impacts"] = []
    return out


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
    train_end_date: str | None = None,
    target_mode: str | None = None,
    feature_selection: str | None = None,
    importance_keep_ratio: float | None = None,
    feature_allowlist_file: Path | None = None,
    save_selected_features_file: Path | None = None,
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
    if train_end_date is not None and str(train_end_date).strip():
        cmd.extend(["--train-end-date", str(train_end_date).strip()])
    if target_mode is not None and str(target_mode).strip():
        cmd.extend(["--target-mode", str(target_mode).strip().lower()])
    if feature_selection is not None and str(feature_selection).strip():
        cmd.extend(["--feature-selection", str(feature_selection).strip().lower()])
    if importance_keep_ratio is not None:
        cmd.extend(["--importance-keep-ratio", str(float(importance_keep_ratio))])
    if feature_allowlist_file is not None:
        cmd.extend(["--feature-allowlist-file", str(feature_allowlist_file)])
    if save_selected_features_file is not None:
        cmd.extend(["--save-selected-features-file", str(save_selected_features_file)])

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
