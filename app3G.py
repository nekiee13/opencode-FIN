# ------------------------
# app3G.py (repo root shim + PivotCalcResult monkeypatch)
# ------------------------
from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import Any, Dict, Iterator


def _ensure_repo_root_on_syspath(repo_root: Path) -> None:
    """
    Ensure repo root is on sys.path so imports like `import src...` and `import compat...`
    work even when launched from an arbitrary working directory.
    """
    root_str = str(repo_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _pivotcalcresult_to_legacy_dict(obj: Any) -> Dict[str, Any]:
    """
    Best-effort conversion of PivotCalcResult-like objects into the legacy dict shape.

    Expected legacy shape:
      {"Classic": {"Pivot": ..., "R1": ..., "S1": ...}, "Fibonacci": {...}, ...}

    Supported source shapes:
      - obj.levels: dict[str, dict[str, float]]
      - obj.pivots: dict[str, dict[str, float]]
      - obj.classic / obj.camarilla / obj.woodie / obj.fibonacci / obj.demark: dict[str, float]
    """
    if obj is None:
        return {}

    if isinstance(obj, dict):
        return obj

    # Direct mapping already present
    levels = getattr(obj, "levels", None)
    if isinstance(levels, dict) and levels:
        return levels

    pivots = getattr(obj, "pivots", None)
    if isinstance(pivots, dict) and pivots:
        return pivots

    out: Dict[str, Any] = {}

    classic = getattr(obj, "classic", None)
    if isinstance(classic, dict) and classic:
        out["Classic"] = classic

    for attr, key in (
        ("camarilla", "Camarilla"),
        ("woodie", "Woodie"),
        ("fibonacci", "Fibonacci"),
        ("demark", "DeMark"),
    ):
        val = getattr(obj, attr, None)
        if isinstance(val, dict) and val:
            out[key] = val

    return out


def _install_pivotcalcresult_mapping() -> None:
    """
    Patch src.utils.pivots.PivotCalcResult at runtime so it behaves like a Mapping.

    This fixes legacy UI code that does:
      - `"Classic" in pivot_data`
      - `pivot_data["Classic"]`

    The patch is applied BEFORE scripts/app3G.py is executed, so no edits are required
    inside scripts/app3G.py.
    """
    try:
        import src.utils.pivots as pivots_mod  # type: ignore
    except Exception:
        # If pivots module cannot be imported yet, skip patch.
        return

    PivotCalcResult = getattr(pivots_mod, "PivotCalcResult", None)
    if PivotCalcResult is None or not isinstance(PivotCalcResult, type):
        return

    # Avoid double-patching
    if getattr(PivotCalcResult, "_fin_mapping_patched", False):
        return

    def __iter__(self) -> Iterator[str]:
        d = _pivotcalcresult_to_legacy_dict(self)
        return iter(d)

    def __len__(self) -> int:
        d = _pivotcalcresult_to_legacy_dict(self)
        return len(d)

    def __getitem__(self, key: str) -> Any:
        d = _pivotcalcresult_to_legacy_dict(self)
        return d[key]

    def __contains__(self, key: object) -> bool:
        d = _pivotcalcresult_to_legacy_dict(self)
        return key in d

    # Attach mapping-like methods dynamically
    setattr(PivotCalcResult, "__iter__", __iter__)
    setattr(PivotCalcResult, "__len__", __len__)
    setattr(PivotCalcResult, "__getitem__", __getitem__)
    setattr(PivotCalcResult, "__contains__", __contains__)
    setattr(PivotCalcResult, "_fin_mapping_patched", True)


def main() -> int:
    """
    Phase-1 shim to preserve legacy root entrypoint location.

    Delegates execution to scripts/app3G.py without requiring scripts/ to be a package.
    Also applies a runtime PivotCalcResult compatibility patch before delegation.
    """
    repo_root = Path(__file__).resolve().parent
    _ensure_repo_root_on_syspath(repo_root)

    # Apply PivotCalcResult mapping patch early (before scripts/app3G imports pivots utilities)
    _install_pivotcalcresult_mapping()

    target = repo_root / "scripts" / "app3G.py"
    if not target.exists():
        raise FileNotFoundError(f"Expected scripts entrypoint at: {target}")

    # Run scripts/app3G.py as __main__ (argparse/help semantics preserved)
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
