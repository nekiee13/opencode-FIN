# ------------------------
# tests\test_compat_thinness_shape.py
# ------------------------
# tests/test_compat_thinness_shape.py
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import pytest


MAX_FUNC_LOC = 25

ALLOWLIST_FUNC_LOC: list[tuple[str, str, int, str]] = []


@dataclass(frozen=True)
class FunctionLocViolation:
    file: Path
    qualname: str
    lineno: int
    end_lineno: int
    loc: int
    max_allowed: int


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


def _allowlisted_max_loc(rel_path: str, func_qualname: str) -> Optional[int]:
    for allow_path, allow_name, allow_max, _just in ALLOWLIST_FUNC_LOC:
        if rel_path.replace("\\", "/") == allow_path.replace("\\", "/") and func_qualname == allow_name:
            return allow_max
    return None


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}

    class ParentVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[ast.AST] = []

        def generic_visit(self, node: ast.AST) -> None:
            if self.stack:
                parents[id(node)] = self.stack[-1]
            self.stack.append(node)
            super().generic_visit(node)
            self.stack.pop()

    ParentVisitor().visit(tree)
    return parents


def _qualname_for(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    parts: list[str] = []
    cur: Optional[ast.AST] = node
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parts.append(cur.name)
        elif isinstance(cur, ast.ClassDef):
            parts.append(cur.name)
        cur = parents.get(id(cur))
    return ".".join(reversed(parts))


def _loc_for_fn(fn: ast.AST) -> Tuple[int, int, int]:
    lineno = int(getattr(fn, "lineno", 0) or 0)
    end_lineno = int(getattr(fn, "end_lineno", 0) or 0)
    if lineno <= 0 or end_lineno <= 0:
        return lineno, end_lineno, 1
    loc = max(1, end_lineno - lineno + 1)
    return lineno, end_lineno, loc


def _scan_file(path: Path, repo_root: Path) -> List[FunctionLocViolation]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    rel = path.relative_to(repo_root).as_posix()

    parents = _build_parent_map(tree)

    violations: List[FunctionLocViolation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        qualname = _qualname_for(node, parents)
        max_allowed = _allowlisted_max_loc(rel, qualname) or MAX_FUNC_LOC
        lineno, end_lineno, loc = _loc_for_fn(node)

        if loc > max_allowed:
            violations.append(
                FunctionLocViolation(
                    file=path,
                    qualname=qualname,
                    lineno=lineno,
                    end_lineno=end_lineno,
                    loc=loc,
                    max_allowed=max_allowed,
                )
            )

    return violations


def _format_violations(violations: Sequence[FunctionLocViolation], repo_root: Path) -> str:
    lines: list[str] = []
    lines.append("Compat thinness policy violation: oversized functions under compat/.")
    lines.append("")
    lines.append(f"Default MAX_FUNC_LOC = {MAX_FUNC_LOC}")
    lines.append("Violations:")
    for v in sorted(violations, key=lambda x: (x.file.as_posix(), x.qualname, x.lineno)):
        rel = v.file.relative_to(repo_root).as_posix()
        lines.append(f"- {rel}:{v.lineno}-{v.end_lineno} :: {v.qualname} = {v.loc} LOC (max {v.max_allowed})")
    lines.append("")
    lines.append("Remediation:")
    lines.append("- Move logic into src/ and leave only delegation + minimal argument adaptation in compat/.")
    lines.append("- If a temporary exception is required, add a documented entry to ALLOWLIST_FUNC_LOC.")
    return "\n".join(lines)


def test_compat_thinness_shape_function_loc() -> None:
    repo_root = _repo_root()
    compat = _compat_dir(repo_root)

    assert compat.exists() and compat.is_dir(), f"Expected compat/ directory at {compat}"

    violations: List[FunctionLocViolation] = []
    for py_file in _iter_python_files(compat):
        violations.extend(_scan_file(py_file, repo_root))

    if violations:
        pytest.fail(_format_violations(violations, repo_root))
