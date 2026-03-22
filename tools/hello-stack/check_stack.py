#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def _status_rank(status: str) -> int:
    if status == "FAIL":
        return 2
    if status == "WARN":
        return 1
    return 0


def _resolve_executable(token: str) -> Path | None:
    candidate = Path(token).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    found = shutil.which(token)
    return Path(found) if found else None


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_binary(name: str, command: str) -> CheckResult:
    resolved = _resolve_executable(command)
    if resolved:
        return CheckResult(name, "PASS", f"{resolved}")
    return CheckResult(name, "FAIL", f"{command} not found")


def check_symlink(path: Path) -> CheckResult:
    if not path.exists() and not path.is_symlink():
        return CheckResult(path.name, "WARN", f"{path} missing")
    if path.is_symlink():
        target = path.resolve(strict=False)
        if target.exists():
            return CheckResult(path.name, "PASS", f"{path} -> {target}")
        return CheckResult(path.name, "FAIL", f"{path} broken -> {target}")
    return CheckResult(path.name, "PASS", f"{path} exists")


def check_mcp_server(name: str, server: dict, required: bool) -> CheckResult:
    enabled = bool(server.get("enabled", False))
    command = server.get("command")
    if not isinstance(command, list) or not command:
        status = "FAIL" if required else "WARN"
        return CheckResult(name, status, "missing command array")

    executable = str(command[0])
    resolved = _resolve_executable(executable)
    if not resolved:
        status = "FAIL" if required and enabled else "WARN"
        return CheckResult(name, status, f"launcher not found: {executable}")

    status = "PASS"
    if required and not enabled:
        status = "WARN"
    detail = f"enabled={enabled} launcher={resolved}"
    return CheckResult(name, status, detail)


def run_checks(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    opencode_dir = root / ".opencode"
    config_path = opencode_dir / "opencode.json"

    results.append(check_binary("opencode", "opencode"))
    results.append(check_binary("uvx", "/home/opencode/.local/bin/uvx"))

    if not config_path.exists():
        results.append(CheckResult("opencode-config", "FAIL", f"missing {config_path}"))
        return results

    try:
        cfg = _read_json(config_path)
    except Exception as exc:  # pragma: no cover - boundary check
        results.append(CheckResult("opencode-config", "FAIL", f"invalid JSON: {exc}"))
        return results

    results.append(CheckResult("opencode-config", "PASS", str(config_path)))

    mcp = cfg.get("mcp", {})
    if not isinstance(mcp, dict):
        results.append(CheckResult("mcp", "FAIL", "mcp section must be an object"))
        return results

    serena = mcp.get("serena")
    if isinstance(serena, dict):
        results.append(check_mcp_server("mcp:serena", serena, required=True))
    else:
        results.append(CheckResult("mcp:serena", "FAIL", "missing serena block"))

    for optional in ("jcodemunch", "jdocmunch"):
        block = mcp.get(optional)
        if isinstance(block, dict):
            results.append(check_mcp_server(f"mcp:{optional}", block, required=False))
        else:
            results.append(CheckResult(f"mcp:{optional}", "WARN", "not configured"))

    for name in ("agent", "config", "context", "plugin", "skills", "tool"):
        results.append(check_symlink(opencode_dir / name))

    return results


def render(results: Iterable[CheckResult]) -> str:
    rows = list(results)
    width = max(len(r.name) for r in rows) if rows else 10
    out = []
    for row in rows:
        out.append(f"{row.status:4}  {row.name.ljust(width)}  {row.detail}")
    return "\n".join(out)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    results = run_checks(root)
    print(render(results))
    worst = max((_status_rank(r.status) for r in results), default=0)
    return 1 if worst >= 2 else 0


if __name__ == "__main__":
    raise SystemExit(main())
