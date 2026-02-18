# ------------------------
# tools/ownership_map_report.py
# ------------------------
"""Ownership map report generator (Phase-1).

Reads `out/ownership_map.json` produced by `tools/ownership_map.py` and writes a
human-readable Markdown report grouped by module, plus a migration checklist
table that can be used as the worklist for Task 1.2 (compat thinning).

Usage (PowerShell/CMD)
----------------------
python tools/ownership_map_report.py --in-json out/ownership_map.json --out-md out/ownership_map.md

Optional:
  --show-entrypoints  Include detected __main__ entrypoints section (default: on)
  --max-rows-per-func Limit example callsite lines per function (default: 10) [reserved; not used in minimal schema]
  --checklist-csv     Also emit a CSV checklist for spreadsheet tracking

Notes
-----
- This script expects the JSON schema emitted by the minimal ownership_map tool:
    {
      "repo_root": "...",
      "compat_functions": [ {"module": "compat/Models.py", "function": "...", "lineno": 123}, ... ],
      "entrypoints": [ {"file": "scripts/app3G.py", "lineno": 10}, ... ]
    }
- The minimal tool does not include call sites or suggested delegates.
  Therefore the report:
    * provides an empty placeholder column for "Target src delegate" and "Notes"
    * provides a deterministic grouping and ordering
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class CompatFnRow:
    module: str
    function: str
    lineno: int


@dataclass(frozen=True)
class EntrypointRow:
    file: str
    lineno: int


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _normalize_path(s: str) -> str:
    return s.replace("\\", "/")


def _read_rows(data: Dict[str, Any]) -> Tuple[List[CompatFnRow], List[EntrypointRow]]:
    compat: List[CompatFnRow] = []
    entrypoints: List[EntrypointRow] = []

    for item in data.get("compat_functions", []) or []:
        try:
            compat.append(
                CompatFnRow(
                    module=_normalize_path(str(item.get("module", ""))),
                    function=str(item.get("function", "")),
                    lineno=int(item.get("lineno", 0) or 0),
                )
            )
        except Exception:
            continue

    for item in data.get("entrypoints", []) or []:
        try:
            entrypoints.append(
                EntrypointRow(
                    file=_normalize_path(str(item.get("file", ""))),
                    lineno=int(item.get("lineno", 0) or 0),
                )
            )
        except Exception:
            continue

    compat.sort(key=lambda x: (x.module, x.lineno, x.function))
    entrypoints.sort(key=lambda x: (x.file, x.lineno))
    return compat, entrypoints


def _group_by_module(rows: Sequence[CompatFnRow]) -> Dict[str, List[CompatFnRow]]:
    g: Dict[str, List[CompatFnRow]] = defaultdict(list)
    for r in rows:
        g[r.module].append(r)
    return dict(g)


def _md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def write_markdown(
    *,
    repo_root: str,
    compat_rows: Sequence[CompatFnRow],
    entrypoints: Sequence[EntrypointRow],
    out_md: Path,
    show_entrypoints: bool,
) -> None:
    _ensure_parent(out_md)

    lines: List[str] = []
    lines.append("# Ownership Map Report (Phase-1)")
    lines.append("")
    lines.append(f"Repo root: `{_md_escape(repo_root)}`")
    lines.append("")
    lines.append("This report is generated from `out/ownership_map.json` and is intended to drive Phase-1 convergence work.")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Compat functions discovered: **{len(compat_rows)}**")
    lines.append(f"- Entrypoints discovered (via `__main__` guard): **{len(entrypoints)}**")
    lines.append("")

    if show_entrypoints:
        lines.append("## Entrypoints")
        lines.append("")
        if not entrypoints:
            lines.append("- (none)")
        else:
            for e in entrypoints:
                lines.append(f"- `{_md_escape(e.file)}` (line {e.lineno})")
        lines.append("")

    lines.append("## Compat surface inventory (grouped by module)")
    lines.append("")

    grouped = _group_by_module(compat_rows)
    for mod in sorted(grouped.keys()):
        lines.append(f"### `{_md_escape(mod)}`")
        lines.append("")
        lines.append("| Function | Line | |")
        lines.append("|---|---:|---|")
        for r in grouped[mod]:
            lines.append(f"| `{_md_escape(r.function)}` | {r.lineno} | |")
        lines.append("")

    lines.append("## Migration checklist (Task 1.2 worklist)")
    lines.append("")
    lines.append("Use this table as the canonical worklist for converting `compat/` into a thin delegation layer.")
    lines.append("Populate the **Target src delegate** column as per-function routing is decided, then track implementation and verification.")
    lines.append("")

    lines.append("| ID | Compat module | Function | Line | Target src delegate | Status | Notes |")
    lines.append("|---:|---|---|---:|---|---|---|")

    for i, r in enumerate(compat_rows, start=1):
        lines.append(
            "| {id} | `{mod}` | `{fn}` | {ln} |  | TODO |  |".format(
                id=i,
                mod=_md_escape(r.module),
                fn=_md_escape(r.function),
                ln=r.lineno,
            )
        )

    lines.append("")
    lines.append("### Status conventions")
    lines.append("")
    lines.append("- TODO: not started")
    lines.append("- IN-PROGRESS: work ongoing")
    lines.append("- DONE: delegation implemented and tests pass")
    lines.append("- BLOCKED: depends on another task/PR")
    lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")


def write_checklist_csv(compat_rows: Sequence[CompatFnRow], out_csv: Path) -> None:
    _ensure_parent(out_csv)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Compat module", "Function", "Line", "Target src delegate", "Status", "Notes"])
        for i, r in enumerate(compat_rows, start=1):
            w.writerow([i, r.module, r.function, r.lineno, "", "TODO", ""])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Generate Markdown report from ownership_map.json")
    ap.add_argument("--in-json", required=True, help="Input JSON path (e.g., out/ownership_map.json)")
    ap.add_argument("--out-md", required=True, help="Output Markdown path (e.g., out/ownership_map.md)")
    ap.add_argument("--checklist-csv", default=None, help="Optional CSV checklist output path")
    ap.add_argument("--show-entrypoints", action="store_true", help="Include entrypoints section (default: on)")
    ap.add_argument("--max-rows-per-func", type=int, default=10, help="Reserved for richer schema; unused for minimal schema.")

    args = ap.parse_args(argv)

    in_json = Path(args.in_json)
    out_md = Path(args.out_md)

    data = _load_json(in_json)
    repo_root = str(data.get("repo_root", ""))

    compat_rows, entrypoints = _read_rows(data)

    # Default behavior: show entrypoints unless explicitly disabled (flag kept for backward CLI compatibility).
    show_entrypoints = True if not hasattr(args, "show_entrypoints") else (bool(args.show_entrypoints) or True)

    write_markdown(
        repo_root=repo_root,
        compat_rows=compat_rows,
        entrypoints=entrypoints,
        out_md=out_md,
        show_entrypoints=show_entrypoints,
    )

    if args.checklist_csv:
        write_checklist_csv(compat_rows, Path(args.checklist_csv))

    print(f"Wrote {out_md}")
    if args.checklist_csv:
        print(f"Wrote {args.checklist_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
