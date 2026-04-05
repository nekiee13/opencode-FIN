from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.config import paths


def load_ann_store_summary(store_path: Path) -> dict[str, Any]:
    if not store_path.exists():
        return {
            "exists": False,
            "rows": 0,
            "latest_as_of_date": None,
            "store_path": str(store_path),
        }

    conn = sqlite3.connect(str(store_path))
    try:
        total_row = conn.execute("SELECT COUNT(*) FROM ann_marker_values").fetchone()
        latest_row = conn.execute(
            "SELECT MAX(as_of_date) FROM ann_marker_values"
        ).fetchone()
        total = int(total_row[0]) if total_row is not None else 0
        latest = (
            str(latest_row[0]) if latest_row and latest_row[0] is not None else None
        )
    finally:
        conn.close()

    return {
        "exists": True,
        "rows": total,
        "latest_as_of_date": latest,
        "store_path": str(store_path),
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
