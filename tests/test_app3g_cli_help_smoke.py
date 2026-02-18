# tests/test_app3g_cli_help_smoke.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ownership_map_includes_app3g(repo_root: Path) -> bool:
    p = repo_root / "out" / "ownership_map.json"
    if not p.exists():
        return False

    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False

    eps = d.get("entrypoints", [])
    if not isinstance(eps, list):
        return False

    def _norm(s: str) -> str:
        return str(s).replace("/", "\\").lstrip(".\\/")

    for e in eps:
        if isinstance(e, dict):
            v = e.get("path") or e.get("file") or e.get("entry") or ""
        else:
            v = str(e)
        if _norm(v).lower() == "scripts\\app3g.py":
            return True

    return False


def test_app3g_help_smoke_fallback_only() -> None:
    """
    Fallback Phase-1 smoke for scripts/app3G.py help mode.

    Skipped when ownership_map-driven entrypoint smoke already covers scripts/app3G.py.
    """
    repo_root = _repo_root()
    if _ownership_map_includes_app3g(repo_root):
        pytest.skip("Covered by ownership_map entrypoint smoke.")

    script = repo_root / "scripts" / "app3G.py"
    assert script.exists(), f"Missing {script}"

    r = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (
        "scripts/app3G.py --help failed\n"
        f"STDOUT:\n{r.stdout}\n"
        f"STDERR:\n{r.stderr}\n"
    )
