# ------------------------
# tools\import_audit.py
# ------------------------
"""
FIN — Import Audit Utility

Purpose
-------
Statically and dynamically audit FIN imports to catch:
- broken / missing modules
- circular-import symptoms
- accidental side effects on import (filesystem mutations are hard to prove statically,
  but we can detect obvious directory creation / file writes during dynamic import)
- unexpected imports of optional heavy dependencies at import time

What it does
------------
1) Static scan:
   - Walk project python files under src/, compat/, scripts/, tools/
   - Parse AST imports (import / from ... import ...)
   - Build a dependency map:
        file -> imported modules (top-level)
   - Report:
        - intra-project imports that resolve to missing files
        - suspicious absolute legacy imports (e.g., "import Constants") if Constants.py absent
        - duplicate module names that can cause shadowing (e.g., compat.py vs compat/ package)

2) Dynamic import test (best-effort):
   - Import selected modules (default: all src.* and compat.* modules)
   - Capture exceptions and report import failures with tracebacks
   - Optional "side-effect probe":
        - monkeypatch Path.mkdir and builtins.open to detect writes during imports
        - this is conservative: it flags any mkdir/open for write modes during import phase

Safety/Constraints
------------------
- This tool should be run in a controlled environment (your venv).
- It does NOT import heavy optional deps intentionally; it only imports your modules.
- If your modules import heavy deps at import time, this will surface in the report.

Usage examples
--------------
# Run full audit (static + dynamic)
  python tools/import_audit.py

# Only static scan
  python tools/import_audit.py --static-only

# Only dynamic imports
  python tools/import_audit.py --dynamic-only

# Restrict dynamic imports to a subset
  python tools/import_audit.py --dynamic-only --include src.models,src.structural,compat

# Enable side-effect probe during dynamic imports
  python tools/import_audit.py --dynamic-only --probe-side-effects

Exit codes
----------
0 = OK (no dynamic import failures; no missing intra-project modules)
1 = Issues detected (missing modules, import failures, or side-effect flags)

Notes
-----
- Root discovery is based on presence of src/ and config/ directories.
- This tool does not require web access.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import importlib
import os
import pkgutil
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


# ----------------------------------------------------------------------
# Bootstrap: locate FIN root, ensure importable
# ----------------------------------------------------------------------

def _bootstrap_fin_root() -> Path:
    here = Path(__file__).resolve()
    for p in (here.parent, *here.parents):
        if (p / "src").exists() and (p / "config").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            return p
    # fallback: assume tools/ under FIN root
    root = here.parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


FIN_ROOT = _bootstrap_fin_root()


# ----------------------------------------------------------------------
# Data structures
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class StaticImportIssue:
    file: Path
    imported: str
    issue: str


@dataclass(frozen=True)
class DynamicImportResult:
    module: str
    ok: bool
    error: Optional[str] = None
    traceback: Optional[str] = None
    side_effects: Optional[List[str]] = None


# ----------------------------------------------------------------------
# File discovery
# ----------------------------------------------------------------------

_DEFAULT_SCAN_DIRS = ("src", "compat", "scripts", "tools")


def _iter_py_files(root: Path, dirs: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for d in dirs:
        base = (root / d).resolve()
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            # Skip virtual envs or caches if they exist inside project by accident
            parts = {x.lower() for x in p.parts}
            if "__pycache__" in parts or ".venv" in parts or "venv" in parts:
                continue
            files.append(p)
    return sorted(set(files))


# ----------------------------------------------------------------------
# Static import extraction
# ----------------------------------------------------------------------

def _module_from_import(node: ast.AST) -> List[str]:
    out: List[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name:
                out.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            # Keep relative markers if present (level > 0)
            if getattr(node, "level", 0):
                out.append("." * int(node.level) + node.module)
            else:
                out.append(node.module)
        else:
            # from . import x
            if getattr(node, "level", 0):
                out.append("." * int(node.level))
    return out


def _extract_imports_from_file(path: Path) -> List[str]:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        # if file is broken, report no imports; dynamic phase will likely catch it too
        return []
    mods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods.extend(_module_from_import(node))
    return mods


def _is_probably_stdlib(module: str) -> bool:
    # heuristic: stdlib modules have no dots or common names; too hard to be perfect
    return module in {
        "os", "sys", "re", "json", "math", "time", "datetime", "pathlib", "typing",
        "logging", "argparse", "subprocess", "itertools", "functools", "dataclasses",
        "traceback", "importlib", "pkgutil", "collections", "statistics", "shutil",
        "tempfile", "threading", "tkinter",
    }


def _strip_relative(module: str) -> str:
    return module.lstrip(".")


def _resolve_intra_project_module(module: str, root: Path) -> Optional[Path]:
    """
    Resolve module -> expected path inside project for intra-project modules.
    Only attempts for modules that begin with 'src' or 'compat' or are likely legacy flat modules.
    """
    m = _strip_relative(module)

    # direct src.* or compat.* style
    if m.startswith("src.") or m == "src":
        rel = Path(*m.split(".")[1:])  # drop 'src'
        # package or module
        cand_mod = (root / "src" / rel).with_suffix(".py")
        cand_pkg = (root / "src" / rel / "__init__.py")
        if cand_mod.exists():
            return cand_mod
        if cand_pkg.exists():
            return cand_pkg
        return None

    if m.startswith("compat.") or m == "compat":
        rel = Path(*m.split(".")[1:])  # drop 'compat'
        cand_mod = (root / "compat" / rel).with_suffix(".py")
        cand_pkg = (root / "compat" / rel / "__init__.py")
        if cand_mod.exists():
            return cand_mod
        if cand_pkg.exists():
            return cand_pkg
        return None

    # legacy flat module import (e.g., Constants, ExoConfig, TDAIndicators)
    # Consider it intra-project if a matching .py exists at root or under compat/
    leaf = m.split(".", 1)[0]
    root_mod = (root / f"{leaf}.py")
    compat_mod = (root / "compat" / f"{leaf}.py")
    if root_mod.exists():
        return root_mod
    if compat_mod.exists():
        return compat_mod

    return None


def run_static_scan(root: Path, scan_dirs: Sequence[str]) -> Tuple[Dict[Path, List[str]], List[StaticImportIssue]]:
    files = _iter_py_files(root, scan_dirs)
    dep_map: Dict[Path, List[str]] = {}
    issues: List[StaticImportIssue] = []

    # detect potential shadowing hazards
    # Example: compat.py file can shadow compat/ package; src.py can shadow src/ package.
    shadow_candidates = [
        ("compat", root / "compat.py", root / "compat"),
        ("src", root / "src.py", root / "src"),
    ]
    for name, modfile, pkgdir in shadow_candidates:
        if modfile.exists() and pkgdir.exists():
            issues.append(
                StaticImportIssue(
                    file=modfile,
                    imported=name,
                    issue=f"Shadowing hazard: both {modfile.name} and {pkgdir.name}/ exist. "
                          f"Python may import the file instead of the package.",
                )
            )

    for f in files:
        imports = _extract_imports_from_file(f)
        dep_map[f] = imports

        for imp in imports:
            base = _strip_relative(imp)
            if not base:
                continue

            # only check intra-project candidates; external libs are out of scope here
            resolved = _resolve_intra_project_module(imp, root)
            if resolved is None:
                # Flag likely intra-project missing modules:
                if base.startswith(("src.", "compat.")) or base in {"src", "compat"}:
                    issues.append(
                        StaticImportIssue(
                            file=f,
                            imported=imp,
                            issue="Intra-project import unresolved (missing module/package).",
                        )
                    )
                else:
                    # legacy flat modules: flag if it looks like a project module and not stdlib
                    leaf = base.split(".", 1)[0]
                    if leaf[0].isupper() and not _is_probably_stdlib(leaf):
                        # e.g., Constants, Models, ExoConfig
                        issues.append(
                            StaticImportIssue(
                                file=f,
                                imported=imp,
                                issue="Suspicious legacy flat import (not found at root or compat/).",
                            )
                        )

    return dep_map, issues


# ----------------------------------------------------------------------
# Dynamic import runner + side-effect probe
# ----------------------------------------------------------------------

class _SideEffectProbe:
    """
    Context manager that detects filesystem writes during import:
    - Path.mkdir calls
    - open(..., mode includes 'w', 'a', '+') calls
    This is best-effort: it cannot detect all writes (e.g., os.makedirs, pathlib.Path.write_text).
    """
    def __init__(self) -> None:
        self.events: List[str] = []
        self._orig_open = builtins.open
        self._orig_mkdir = Path.mkdir

    def _patched_open(self, file, mode="r", *args, **kwargs):  # type: ignore[override]
        try:
            m = str(mode)
            if any(x in m for x in ("w", "a", "+", "x")):
                self.events.append(f"open(write): {file} mode={mode}")
        except Exception:
            pass
        return self._orig_open(file, mode, *args, **kwargs)

    def _patched_mkdir(self, self_path: Path, *args, **kwargs):  # type: ignore[override]
        try:
            self.events.append(f"mkdir: {self_path}")
        except Exception:
            pass
        return self._orig_mkdir(self_path, *args, **kwargs)

    def __enter__(self) -> "_SideEffectProbe":
        builtins.open = self._patched_open  # type: ignore[assignment]
        Path.mkdir = self._patched_mkdir  # type: ignore[assignment]
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        builtins.open = self._orig_open  # type: ignore[assignment]
        Path.mkdir = self._orig_mkdir  # type: ignore[assignment]


def _iter_importable_modules(root: Path, include_prefixes: Sequence[str]) -> List[str]:
    """
    Discover importable modules under src and compat packages.
    include_prefixes controls which roots are included, e.g. ["src", "compat"].
    """
    mods: List[str] = []

    def discover(pkg_name: str, pkg_dir: Path) -> None:
        if not pkg_dir.exists():
            return
        # Ensure package init exists; otherwise import discovery is ambiguous
        init = pkg_dir / "__init__.py"
        if not init.exists():
            return

        for m in pkgutil.walk_packages([str(pkg_dir)], prefix=f"{pkg_name}."):
            mods.append(m.name)

    if any(p == "src" or p.startswith("src") for p in include_prefixes):
        discover("src", root / "src")
    if any(p == "compat" or p.startswith("compat") for p in include_prefixes):
        discover("compat", root / "compat")

    # Allow including single modules explicitly (e.g., "scripts.workers")
    extra: Set[str] = set()
    for p in include_prefixes:
        p = p.strip().strip(".")
        if p and p not in {"src", "compat"} and "." in p:
            extra.add(p)
    mods.extend(sorted(extra))

    # De-dup + stable
    return sorted(set(mods))


def run_dynamic_imports(
    modules: Sequence[str],
    *,
    probe_side_effects: bool,
) -> List[DynamicImportResult]:
    results: List[DynamicImportResult] = []

    for mod in modules:
        side_events: Optional[List[str]] = None
        try:
            if probe_side_effects:
                with _SideEffectProbe() as probe:
                    importlib.invalidate_caches()
                    importlib.import_module(mod)
                    side_events = list(probe.events)
            else:
                importlib.invalidate_caches()
                importlib.import_module(mod)

            results.append(DynamicImportResult(module=mod, ok=True, side_effects=side_events))
        except Exception as e:
            tb = traceback.format_exc()
            results.append(
                DynamicImportResult(
                    module=mod,
                    ok=False,
                    error=f"{type(e).__name__}: {e}",
                    traceback=tb,
                    side_effects=side_events,
                )
            )

    return results


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------

def _print_static_report(dep_map: Dict[Path, List[str]], issues: List[StaticImportIssue]) -> None:
    print("\n====================")
    print("STATIC IMPORT SCAN")
    print("====================")
    print(f"FIN_ROOT: {FIN_ROOT}")
    print(f"Files scanned: {len(dep_map)}")

    if not issues:
        print("No static issues detected.")
        return

    print(f"\nStatic issues: {len(issues)}")
    for i, iss in enumerate(issues, 1):
        print(f"\n--- STATIC ISSUE {i} ---")
        print(f"File:     {iss.file}")
        print(f"Import:   {iss.imported}")
        print(f"Issue:    {iss.issue}")


def _print_dynamic_report(results: List[DynamicImportResult]) -> None:
    print("\n====================")
    print("DYNAMIC IMPORT TEST")
    print("====================")
    print(f"Modules tested: {len(results)}")

    failures = [r for r in results if not r.ok]
    side_effect_flags = [r for r in results if r.ok and r.side_effects]

    if not failures:
        print("No dynamic import failures detected.")
    else:
        print(f"\nDynamic failures: {len(failures)}")
        for i, r in enumerate(failures, 1):
            print(f"\n--- DYNAMIC FAILURE {i} ---")
            print(f"Module: {r.module}")
            print(f"Error:  {r.error}")
            if r.traceback:
                print("Traceback:")
                print(r.traceback)

    if side_effect_flags:
        print(f"\nSide-effect signals during import: {len(side_effect_flags)}")
        for i, r in enumerate(side_effect_flags, 1):
            print(f"\n--- SIDE EFFECT {i} ---")
            print(f"Module: {r.module}")
            for ev in (r.side_effects or [])[:50]:
                print(f"  - {ev}")
            if r.side_effects and len(r.side_effects) > 50:
                print(f"  ... ({len(r.side_effects) - 50} more)")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FIN import audit (static + dynamic).")

    p.add_argument("--static-only", action="store_true", help="Run only static scan.")
    p.add_argument("--dynamic-only", action="store_true", help="Run only dynamic imports.")
    p.add_argument(
        "--scan-dirs",
        nargs="*",
        default=list(_DEFAULT_SCAN_DIRS),
        help="Directories (relative to FIN root) to scan statically. Default: src compat scripts tools",
    )
    p.add_argument(
        "--include",
        nargs="*",
        default=["src", "compat"],
        help="Top-level module roots to include for dynamic imports. Default: src compat. "
             "You can also pass specific modules like 'scripts.workers.app3GTI'.",
    )
    p.add_argument(
        "--probe-side-effects",
        action="store_true",
        help="Detect mkdir/open-for-write calls during import (best-effort).",
    )

    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.static_only and args.dynamic_only:
        raise SystemExit("Choose at most one of --static-only or --dynamic-only.")

    do_static = not args.dynamic_only
    do_dynamic = not args.static_only

    static_issues: List[StaticImportIssue] = []
    dynamic_results: List[DynamicImportResult] = []

    if do_static:
        dep_map, static_issues = run_static_scan(FIN_ROOT, scan_dirs=tuple(args.scan_dirs))
        _print_static_report(dep_map, static_issues)

    if do_dynamic:
        modules = _iter_importable_modules(FIN_ROOT, include_prefixes=tuple(args.include))
        # Avoid importing tools.* by default, unless user asked; importing tools can
        # create circularities if they are scripts rather than packages.
        # The user can explicitly include them via --include.
        modules = [m for m in modules if not m.startswith("tools.")]

        dynamic_results = run_dynamic_imports(modules, probe_side_effects=bool(args.probe_side_effects))
        _print_dynamic_report(dynamic_results)

    # Determine exit status
    dynamic_fail = any((not r.ok) for r in dynamic_results)
    missing_mods = any(("missing" in iss.issue.lower() or "unresolved" in iss.issue.lower()) for iss in static_issues)

    if dynamic_fail or missing_mods:
        print("\nRESULT: ISSUES DETECTED")
        return 1

    print("\nRESULT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
