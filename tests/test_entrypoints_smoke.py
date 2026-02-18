# tests/test_entrypoints_smoke.py
from __future__ import annotations

import json
import importlib.util
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _env_with_repo_pythonpath(repo_root: Path) -> Dict[str, str]:
    """
    Ensures src.* is importable for scripts that do not self-bootstrap sys.path.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo_root) + (os.pathsep + existing if existing else "")
    return env


def _has_tkinter() -> bool:
    return importlib.util.find_spec("tkinter") is not None


def _ensure_ownership_map(repo_root: Path) -> Path:
    """
    Ensures out/ownership_map.json exists.

    If missing, tools/ownership_map.py is executed to generate it.
    """
    out_json = repo_root / "out" / "ownership_map.json"
    if out_json.exists():
        return out_json

    tool = repo_root / "tools" / "ownership_map.py"
    assert tool.exists(), f"Missing ownership map generator at {tool}"

    out_json.parent.mkdir(parents=True, exist_ok=True)

    r = subprocess.run(
        [sys.executable, str(tool)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=120,
        env=_env_with_repo_pythonpath(repo_root),
    )
    assert r.returncode == 0, (
        "Ownership map generation failed.\n"
        f"CMD: {sys.executable} {tool}\n"
        f"STDOUT:\n{r.stdout}\n"
        f"STDERR:\n{r.stderr}\n"
    )
    assert out_json.exists(), f"Ownership map not created at {out_json}"
    return out_json


def _load_entrypoints(repo_root: Path) -> List[str]:
    """
    Ownership map is the authoritative source of entrypoints.
    Dict and string formats are accepted.
    """
    p = _ensure_ownership_map(repo_root)
    d: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    eps = d.get("entrypoints", [])
    assert isinstance(eps, list), "ownership_map.json: 'entrypoints' must be a list"

    out: List[str] = []
    for e in eps:
        if isinstance(e, dict):
            v = e.get("path") or e.get("file") or e.get("entry") or ""
        else:
            v = str(e)
        v = str(v).strip().replace("\\", "/").lstrip("./\\")
        if v:
            out.append(v)

    # Stable de-duplication
    seen: set[str] = set()
    uniq: List[str] = []
    for v in out:
        if v not in seen:
            uniq.append(v)
            seen.add(v)
    return uniq


def test_entrypoints_exist_from_ownership_map() -> None:
    repo_root = _repo_root()
    eps = _load_entrypoints(repo_root)
    assert eps, "ownership_map.json contains no entrypoints"

    missing = [e for e in eps if not (repo_root / e).exists()]
    assert not missing, f"Entrypoints listed but missing on disk: {missing}"


def _run_help(repo_root: Path, rel_path: str, timeout_s: int = 45) -> None:
    """
    Executes a script in help mode via subprocess.

    Test harness sets PYTHONPATH=repo_root to reduce per-entrypoint bootstrap requirements.
    """
    env = _env_with_repo_pythonpath(repo_root)
    cmd = [sys.executable, rel_path, "--help"]

    r = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=env,
    )

    if r.returncode != 0:
        raise AssertionError(
            f"{rel_path} --help failed with code={r.returncode}\n"
            f"CMD: {' '.join(cmd)}\n"
            f"STDOUT:\n{r.stdout}\n"
            f"STDERR:\n{r.stderr}\n"
        )


def _run_runpy(repo_root: Path, rel_path: str) -> None:
    """
    Executes a python file as __main__ in-process.

    SystemExit is accepted to accommodate argparse-style exits.
    """
    rel_fs = rel_path.replace("\\", "/")
    target = repo_root / rel_fs
    assert target.exists(), f"Missing entrypoint: {rel_fs}"

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    old_cwd = os.getcwd()
    try:
        os.chdir(str(repo_root))
        try:
            runpy.run_path(str(target), run_name="__main__")
        except SystemExit:
            pass
    finally:
        os.chdir(old_cwd)


def test_entrypoints_startup_smoke() -> None:
    """
    Phase-1 smoke: entrypoints must start without import-time crashes.

    Policy:
    - scripts\\ and tools\\ : prefer '--help' subprocess (fast, minimal)
    - other paths           : runpy execution
    """
    repo_root = _repo_root()
    eps = _load_entrypoints(repo_root)

    for rel in eps:
        rel = rel.replace("\\", "/")
        if not _has_tkinter() and rel.lower().endswith("app3g.py"):
            continue
        assert (repo_root / rel).exists(), f"Missing entrypoint: {rel}"

        if rel.startswith(("scripts/", "tools/")):
            _run_help(repo_root, rel)
        else:
            _run_runpy(repo_root, rel)
