# ------------------------
# src/utils/tmp_artifacts.py
# ------------------------
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

def _truthy_env(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")

def get_debug_root(default_root: Optional[Path] = None) -> Path:
    """
    Returns a stable debug root directory.

    Priority:
    1) FIN_DEBUG_DIR env var
    2) <repo_root>/debug_artifacts
    3) default_root if provided
    """
    env = os.environ.get("FIN_DEBUG_DIR", "").strip()
    if env:
        return Path(env)

    if default_root is not None:
        return default_root

    # repo_root = .../src/utils/tmp_artifacts.py -> parents[2] == repo root
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "debug_artifacts"

def make_work_dir(prefix: str = "fin_", *, repo_root: Optional[Path] = None) -> Tuple[Path, bool]:
    """
    Creates a working directory.
    Returns: (path, keep)

    keep=True when FIN_KEEP_TEMP=1, meaning caller should NOT delete artifacts.
    """
    keep = _truthy_env("FIN_KEEP_TEMP")

    if keep:
        base = get_debug_root((repo_root / "debug_artifacts") if repo_root else None) / "temp"
        base.mkdir(parents=True, exist_ok=True)
        p = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))
        return p, True

    # default temp behavior
    p = Path(tempfile.mkdtemp(prefix=prefix))
    return p, False
