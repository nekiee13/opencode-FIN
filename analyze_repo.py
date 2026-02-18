#!/usr/bin/env python3
"""Repository Architecture Analyzer (static, no code execution)

Outputs are written to ./out:
- tree.json
- summary.json
- symbols_index.json
- import_graph.json
- ARCHITECTURE.md

Design constraints:
- Static analysis only (AST parsing, filesystem metadata).
- No imports from the target repository modules.
- Deterministic output ordering.
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


OUT_DIRNAME = "out"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_read_text(p: Path, limit_bytes: int = 2_000_000) -> str:
    """Read text with a hard size cap. Binary-ish content is ignored."""
    try:
        b = p.read_bytes()
    except Exception:
        return ""
    if len(b) > limit_bytes:
        b = b[:limit_bytes]
    try:
        return b.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _rel(p: Path, root: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except Exception:
        return p.as_posix()


def _mkdir(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_size_bytes(p: Path) -> int:
    try:
        return p.stat().st_size
    except Exception:
        return 0


def build_tree(root: Path, max_entries: int = 200_000) -> Dict[str, Any]:
    """Capture file/folder tree with basic metadata."""
    entries: List[Dict[str, Any]] = []
    count = 0

    for p in sorted(root.rglob("*"), key=lambda x: x.as_posix()):
        if count >= max_entries:
            break
        try:
            is_dir = p.is_dir()
            is_file = p.is_file()
        except Exception:
            continue

        if not (is_dir or is_file):
            continue

        item = {
            "path": _rel(p, root),
            "type": "dir" if is_dir else "file",
        }
        if is_file:
            item["size_bytes"] = _file_size_bytes(p)
            item["suffix"] = p.suffix.lower()
        entries.append(item)
        count += 1

    return {
        "root": root.as_posix(),
        "captured_at_utc": _utc_iso(),
        "entries_total": len(entries),
        "truncated": count >= max_entries,
        "entries": entries,
    }


def summarize_repo(root: Path, tree: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize extensions, markers, and high-level structure."""
    files = [e for e in tree["entries"] if e["type"] == "file"]
    dirs = [e for e in tree["entries"] if e["type"] == "dir"]

    ext_counts = Counter((e.get("suffix") or "NOEXT") for e in files)
    top_ext = ext_counts.most_common(30)

    markers = [
        "pyproject.toml",
        "pytest.ini",
        "requirements.txt",
        "setup.cfg",
        "setup.py",
        "package.json",
        "poetry.lock",
        "Pipfile",
        "Pipfile.lock",
        "Dockerfile",
        "docker-compose.yml",
        "compose.yml",
        ".env",
    ]
    present_markers = [m for m in markers if (root / m).exists()]

    entry_candidates: List[str] = []
    for e in files:
        pth = e["path"]
        if not pth.endswith(".py"):
            continue
        name = Path(pth).name.lower()
        if name in {"app.py", "main.py", "__main__.py"}:
            entry_candidates.append(pth)
        if name.startswith("app") and name.endswith(".py"):
            entry_candidates.append(pth)
        if name.endswith("cli.py"):
            entry_candidates.append(pth)

    entry_candidates = sorted(set(entry_candidates))

    top_dirs = sorted({Path(d["path"]).parts[0] for d in dirs if d["path"] and d["path"] != "."})

    return {
        "captured_at_utc": tree.get("captured_at_utc"),
        "files_total": len(files),
        "dirs_total": len(dirs),
        "top_level_dirs": top_dirs,
        "top_extensions": [{"ext": k, "count": v} for k, v in top_ext],
        "markers_present": present_markers,
        "entry_candidates": entry_candidates,
    }


def _ast_symbols_for_file(py_path: Path, rel_path: str) -> Dict[str, Any]:
    """Extract top-level AST symbols (classes/functions) plus a limited set of module constants."""
    src = _safe_read_text(py_path)
    if not src:
        return {"error": "unreadable_or_empty", "symbols": []}

    try:
        t = ast.parse(src, filename=rel_path)
    except Exception as e:
        return {"error": f"parse_error: {e}", "symbols": []}

    symbols: List[Dict[str, Any]] = []
    for n in t.body:
        if isinstance(n, ast.ClassDef):
            symbols.append({"kind": "class", "name": n.name, "line": getattr(n, "lineno", None)})
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append({"kind": "function", "name": n.name, "line": getattr(n, "lineno", None)})
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets: List[str] = []
            if isinstance(n, ast.Assign):
                for tg in n.targets:
                    if isinstance(tg, ast.Name):
                        targets.append(tg.id)
            else:
                if isinstance(n.target, ast.Name):
                    targets.append(n.target.id)
            for name in targets[:10]:
                symbols.append({"kind": "assign", "name": name, "line": getattr(n, "lineno", None)})

    return {"symbols": symbols}


def build_symbols_index(root: Path) -> Dict[str, Any]:
    """Build symbols index for all Python files."""
    py_files = sorted([p for p in root.rglob("*.py") if p.is_file()], key=lambda x: x.as_posix())
    idx: Dict[str, Any] = {}
    for p in py_files:
        rp = _rel(p, root)
        idx[rp] = _ast_symbols_for_file(p, rp)
    return {
        "captured_at_utc": _utc_iso(),
        "python_files_total": len(py_files),
        "files": idx,
    }


def build_import_graph(root: Path) -> Dict[str, Any]:
    """Build per-file import graph using AST top-level import nodes."""
    py_files = sorted([p for p in root.rglob("*.py") if p.is_file()], key=lambda x: x.as_posix())
    graph: Dict[str, Any] = {}

    for p in py_files:
        rp = _rel(p, root)
        src = _safe_read_text(p)
        if not src:
            graph[rp] = {"error": "unreadable_or_empty", "imports": [], "from_imports": []}
            continue
        try:
            t = ast.parse(src, filename=rp)
        except Exception as e:
            graph[rp] = {"error": f"parse_error: {e}", "imports": [], "from_imports": []}
            continue

        imps: List[str] = []
        froms: List[Dict[str, Any]] = []
        for n in t.body:
            if isinstance(n, ast.Import):
                for a in n.names:
                    imps.append(a.name)
            elif isinstance(n, ast.ImportFrom):
                mod = n.module or ""
                lvl = n.level or 0
                names = [a.name for a in n.names]
                froms.append({"module": mod, "level": lvl, "names": names})

        graph[rp] = {
            "imports": sorted(set(imps)),
            "from_imports": froms,
        }

    return {
        "captured_at_utc": _utc_iso(),
        "python_files_total": len(py_files),
        "graph": graph,
    }


def _component_guess(path: str) -> str:
    parts = Path(path).parts
    if not parts:
        return "other"
    if parts[0] == "tests":
        return "tests"
    if parts[0] == "data":
        return "data"
    if parts[0] == "docs":
        return "docs"
    if parts[0] == "config":
        return "config"
    if parts[0] == "scripts":
        return "scripts"
    if parts[0] == "src" and len(parts) > 1:
        return f"src/{parts[1]}"
    if parts[0] == "src":
        return "src"
    return parts[0]


def generate_architecture_md(summary: Dict[str, Any], symbols: Dict[str, Any]) -> str:
    files_by_component: Dict[str, List[str]] = defaultdict(list)
    for fpath in symbols.get("files", {}).keys():
        files_by_component[_component_guess(fpath)].append(fpath)
    for k in list(files_by_component.keys()):
        files_by_component[k] = sorted(files_by_component[k])

    sym_counts: List[Tuple[int, str]] = []
    for fpath, info in symbols.get("files", {}).items():
        syms = info.get("symbols", []) if isinstance(info, dict) else []
        sym_counts.append((len(syms), fpath))
    sym_counts.sort(reverse=True)
    central = sym_counts[:10]

    lines: List[str] = []
    lines.append("# Repository Architecture Overview")
    lines.append("")
    lines.append(f"Generated: `{_utc_iso()}`")
    lines.append("")
    lines.append("## High-level structure")
    lines.append("")
    lines.append("Top-level folders:")
    for d in summary.get("top_level_dirs", []):
        lines.append(f"- `{d}/`")
    lines.append("")
    lines.append("Key entry point candidates:")
    for e in summary.get("entry_candidates", [])[:20]:
        lines.append(f"- `{e}`")
    lines.append("")
    lines.append("## Components (path-based grouping)")
    lines.append("")
    lines.append("Components are inferred from folder layout. This is a heuristic grouping.")
    lines.append("")
    for comp in sorted(files_by_component.keys()):
        lines.append(f"### `{comp}`")
        lines.append(f"Python modules: {len(files_by_component[comp])}")
        for f in files_by_component[comp][:15]:
            lines.append(f"- `{f}`")
        if len(files_by_component[comp]) > 15:
            lines.append(f"- ? ({len(files_by_component[comp]) - 15} more)")
        lines.append("")
    lines.append("## Central modules (symbol-count heuristic)")
    lines.append("")
    for n, f in central:
        lines.append(f"- `{f}` (symbols: {n})")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Static-only analysis was performed (filesystem + Python AST).")
    lines.append("- Import edges are exported to `out/import_graph.json` for graphing and cycle checks.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: List[str]) -> int:
    root = Path(".").resolve()
    out_dir = root / OUT_DIRNAME
    _mkdir(out_dir)

    tree = build_tree(root)
    summary = summarize_repo(root, tree)
    symbols = build_symbols_index(root)
    import_graph = build_import_graph(root)

    _write_json(out_dir / "tree.json", tree)
    _write_json(out_dir / "summary.json", summary)
    _write_json(out_dir / "symbols_index.json", symbols)
    _write_json(out_dir / "import_graph.json", import_graph)

    arch_md = generate_architecture_md(summary, symbols)
    (out_dir / "ARCHITECTURE.md").write_text(arch_md, encoding="utf-8")

    print("WROTE", str(out_dir / "tree.json"))
    print("WROTE", str(out_dir / "summary.json"))
    print("WROTE", str(out_dir / "symbols_index.json"))
    print("WROTE", str(out_dir / "import_graph.json"))
    print("WROTE", str(out_dir / "ARCHITECTURE.md"))
    print("ANALYZE_REPO_PY_WRITTEN_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
