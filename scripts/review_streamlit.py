from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_sys_path() -> Path:
    this_file = Path(__file__).resolve()
    scripts_dir = this_file.parent
    app_root = scripts_dir.parent
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    return app_root


APP_ROOT = _bootstrap_sys_path()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch FIN Streamlit review console",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite path override for HITL review store",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        from src.ui.review_streamlit import run_review_console
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "") or "dependency"
        print(f"Failed to import review console dependency: {missing}")
        print("Install Streamlit and retry: python -m pip install streamlit")
        return 2

    db_path = Path(args.db_path).resolve() if args.db_path else None
    run_review_console(db_path=db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
