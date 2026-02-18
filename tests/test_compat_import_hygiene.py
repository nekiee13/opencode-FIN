# ------------------------
# tests\test_compat_import_hygiene.py
# ------------------------
# tests/test_compat_import_hygiene.py
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import pytest


FORBIDDEN_IMPORT_ROOTS = {
    # time-series / econometrics
    "pmdarima",
    "statsmodels",
    "arch",
    # ML / DL
    "tensorflow",
    "keras",
    "torch",
    "sklearn",
    "xgboost",
    "lightgbm",
    "catboost",
    # auto-ML / workflow
    "pycaret",
    # probabilistic programming / Bayesian
    "pymc",
    "pystan",
    "stan",
}

# Explicit exceptions are discouraged.
# Format: {"module_root": [("compat/relative/path.py", "justification"), ...]}
ALLOWLIST_EXCEPTIONS: dict[str, list[tuple[str, str]]] = {}


@dataclass(frozen=True)
class ImportViolation:
    file: Path
    lineno: int
    col_offset: int
    imported_root: str
    raw: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _compat_dir(repo_root: Path) -> Path:
    return repo_root / "compat"


def _iter_python_files(root: Path) -> Iterable[Path]:
    exclude_parts = {"__pycache__", ".pytest_cache", ".mypy_cache"}
    for p in root.rglob("*.py"):
        if any(part in exclude_parts for part in p.parts):
            continue
        yield p


def _is_allowlisted(import_root: str, rel_path: str) -> Optional[str]:
    for allowed_path, justification in ALLOWLIST_EXCEPTIONS.get(import_root, []):
        if rel_path.replace("\\", "/") == allowed_path.replace("\\", "/"):
            return justification
    return None


def _collect_import_roots(tree: ast.AST) -> List[Tuple[str, ast.AST]]:
    imports: List[Tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = (alias.name or "").split(".")[0]
                if root:
                    imports.append((root, node))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root:
                    imports.append((root, node))
    return imports


def _node_raw_line(src: str, node: ast.AST) -> str:
    lineno = getattr(node, "lineno", None)
    if not lineno:
        return ""
    lines = src.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


def _scan_file(path: Path, repo_root: Path) -> List[ImportViolation]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    rel = path.relative_to(repo_root).as_posix()

    violations: List[ImportViolation] = []
    for import_root, node in _collect_import_roots(tree):
        if import_root not in FORBIDDEN_IMPORT_ROOTS:
            continue
        if _is_allowlisted(import_root, rel) is not None:
            continue

        violations.append(
            ImportViolation(
                file=path,
                lineno=int(getattr(node, "lineno", 0) or 0),
                col_offset=int(getattr(node, "col_offset", 0) or 0),
                imported_root=import_root,
                raw=_node_raw_line(src, node),
            )
        )

    return violations


def _format_violations(violations: Sequence[ImportViolation], repo_root: Path) -> str:
    lines: list[str] = []
    lines.append("Forbidden imports detected under compat/. Phase-1 policy violation.")
    lines.append("")
    lines.append("Violations:")
    for v in sorted(violations, key=lambda x: (x.file.as_posix(), x.lineno, x.col_offset)):
        rel = v.file.relative_to(repo_root).as_posix()
        snippet = f" | {v.raw}" if v.raw else ""
        lines.append(f"- {rel}:{v.lineno}:{v.col_offset} imports '{v.imported_root}'{snippet}")
    lines.append("")
    lines.append("Remediation:")
    lines.append("- Move modeling logic into src/ and convert compat/ into delegation-only stubs.")
    lines.append("- If a temporary exception is required, add an allowlist entry with a removal milestone.")
    return "\n".join(lines)


def test_compat_import_hygiene() -> None:
    repo_root = _repo_root()
    compat = _compat_dir(repo_root)

    assert compat.exists() and compat.is_dir(), f"Expected compat/ directory at {compat}"

    violations: List[ImportViolation] = []
    for py_file in _iter_python_files(compat):
        violations.extend(_scan_file(py_file, repo_root))

    if violations:
        pytest.fail(_format_violations(violations, repo_root))
