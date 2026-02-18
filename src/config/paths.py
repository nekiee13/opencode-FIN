# ------------------------
# src\config\paths.py
# ------------------------
"""
FIN Path Stabilization Layer (Refactor Phase 1)

This module is the single source-of-truth for resolving project-relative paths.

Design goals:
- Robust root discovery (works from any current working directory).
- Zero filesystem mutation on import (no mkdir, no writes).
- Explicit directory creation via ensure_directories().
- Support legacy/transition entrypoints and worker resolution.

Project layout (expected):
FIN/
  config/Exo_regressors.csv
  data/raw/*.csv
  data/artifacts/{svl,tda}/
  graphs/
  logs/
  out/
  scripts/
    workers/
  src/

If the project root cannot be discovered, get_project_root() fails fast.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional


# ----------------------------
# Root discovery
# ----------------------------

# Anchor files/paths that indicate the project root. Add more if you introduce them.
_ROOT_ANCHORS: tuple[str, ...] = (
    os.path.join("config", "Exo_regressors.csv"),
    # Transitional/compat: allow legacy root anchor (kept for migration convenience)
    "Exo_regressors.csv",
    # Packaging marker (helps if you later ship as a package)
    "pyproject.toml",
)


def _has_any_anchor(candidate_root: Path, anchors: Iterable[str]) -> bool:
    """Return True if candidate_root contains any of the anchor paths."""
    for rel in anchors:
        try:
            if (candidate_root / rel).exists():
                return True
        except OSError:
            # Defensive: ignore unreadable paths
            continue
    return False


def get_project_root(start: Optional[Path] = None) -> Path:
    """Discover the project root by walking upward until an anchor is found.

    Parameters
    ----------
    start:
        Starting path for the search. Defaults to this file's directory.

    Returns
    -------
    Path
        The resolved project root.

    Raises
    ------
    RuntimeError
        If no anchor is found.
    """
    start_path = (start or Path(__file__)).resolve()
    cur = start_path if start_path.is_dir() else start_path.parent

    # Walk upward to filesystem root.
    for parent in (cur, *cur.parents):
        if _has_any_anchor(parent, _ROOT_ANCHORS):
            return parent

    raise RuntimeError(
        "Unable to resolve project root. Searched upward from: "
        f"{cur}. Expected one of the anchors: {list(_ROOT_ANCHORS)}"
    )


# ----------------------------
# Exported paths (side-effect free)
# ----------------------------

APP_ROOT: Path = get_project_root()
SRC_DIR: Path = APP_ROOT / "src"

CONFIG_DIR: Path = APP_ROOT / "config"
# Transitional/compat config location
LEGACY_CONFIG_DIR: Path = APP_ROOT

DATA_DIR: Path = APP_ROOT / "data"
DATA_RAW_DIR: Path = DATA_DIR / "raw"

ARTIFACTS_DIR: Path = DATA_DIR / "artifacts"
SVL_ARTIFACTS_DIR: Path = ARTIFACTS_DIR / "svl"
TDA_ARTIFACTS_DIR: Path = ARTIFACTS_DIR / "tda"

OUTPUT_DIR: Path = APP_ROOT / "out"
GRAPHS_DIR: Path = APP_ROOT / "graphs"
LOGS_DIR: Path = APP_ROOT / "logs"

SCRIPTS_DIR: Path = APP_ROOT / "scripts"
WORKERS_DIR: Path = SCRIPTS_DIR / "workers"


def get_exo_config_path() -> Path:
    """Return the canonical Exo_regressors.csv path.

    Priority:
    1) FIN normalized location: config/Exo_regressors.csv
    2) Transitional legacy location: <root>/Exo_regressors.csv

    This function does not validate the file contents; it only resolves location.
    """
    preferred = CONFIG_DIR / "Exo_regressors.csv"
    if preferred.exists():
        return preferred

    legacy = LEGACY_CONFIG_DIR / "Exo_regressors.csv"
    if legacy.exists():
        return legacy

    # If neither exists, return preferred path (so callers can show a consistent error).
    return preferred


EXO_CONFIG_PATH: Path = get_exo_config_path()


# ----------------------------
# Explicit directory creation
# ----------------------------

_DEFAULT_DIRS_TO_ENSURE: tuple[Path, ...] = (
    CONFIG_DIR,
    DATA_DIR,
    DATA_RAW_DIR,
    ARTIFACTS_DIR,
    SVL_ARTIFACTS_DIR,
    TDA_ARTIFACTS_DIR,
    OUTPUT_DIR,
    GRAPHS_DIR,
    LOGS_DIR,
    SCRIPTS_DIR,
    WORKERS_DIR,
)


def ensure_directories(dirs: Optional[Iterable[Path]] = None) -> None:
    """Create required directories.

    IMPORTANT: This must be called explicitly by entrypoints or tests.

    Parameters
    ----------
    dirs:
        Optional iterable of directories to create. If None, uses defaults.
    """
    for d in (dirs or _DEFAULT_DIRS_TO_ENSURE):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Failed to create directory: {d}. Error: {e}") from e


# ----------------------------
# Worker script resolution
# ----------------------------

def get_worker_script_path(script_name: str) -> Path:
    """Resolve a worker script path.

    Resolution order:
    1) scripts/workers/<script_name>
    2) <root>/<script_name>   (legacy fallback)

    Notes
    -----
    - script_name may be given with or without '.py'.
    - This function does not execute the worker; it only resolves location.

    Raises
    ------
    FileNotFoundError
        If the worker cannot be located.
    """
    name = script_name
    if not name.endswith(".py"):
        name += ".py"

    primary = WORKERS_DIR / name
    if primary.exists():
        return primary

    legacy = APP_ROOT / name
    if legacy.exists():
        return legacy

    raise FileNotFoundError(
        f"Worker script not found: {script_name}. Looked in {primary} and {legacy}."
    )


# ----------------------------
# Convenience: expose a dict for quick introspection
# ----------------------------

PATHS = {
    "APP_ROOT": APP_ROOT,
    "SRC_DIR": SRC_DIR,
    "CONFIG_DIR": CONFIG_DIR,
    "EXO_CONFIG_PATH": EXO_CONFIG_PATH,
    "DATA_DIR": DATA_DIR,
    "DATA_RAW_DIR": DATA_RAW_DIR,
    "ARTIFACTS_DIR": ARTIFACTS_DIR,
    "SVL_ARTIFACTS_DIR": SVL_ARTIFACTS_DIR,
    "TDA_ARTIFACTS_DIR": TDA_ARTIFACTS_DIR,
    "OUTPUT_DIR": OUTPUT_DIR,
    "GRAPHS_DIR": GRAPHS_DIR,
    "LOGS_DIR": LOGS_DIR,
    "SCRIPTS_DIR": SCRIPTS_DIR,
    "WORKERS_DIR": WORKERS_DIR,
}


__all__ = [
    "APP_ROOT",
    "SRC_DIR",
    "CONFIG_DIR",
    "DATA_DIR",
    "DATA_RAW_DIR",
    "ARTIFACTS_DIR",
    "SVL_ARTIFACTS_DIR",
    "TDA_ARTIFACTS_DIR",
    "OUTPUT_DIR",
    "GRAPHS_DIR",
    "LOGS_DIR",
    "SCRIPTS_DIR",
    "WORKERS_DIR",
    "EXO_CONFIG_PATH",
    "PATHS",
    "get_project_root",
    "ensure_directories",
    "get_worker_script_path",
    "get_exo_config_path",
]
