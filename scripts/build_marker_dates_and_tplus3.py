from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_sys_path() -> Path:
    this_file = Path(__file__).resolve()
    app_root = this_file.parents[1]
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    return app_root


APP_ROOT = _bootstrap_sys_path()

from src.config import paths  # noqa: E402
from src.data.marker_calendar import generate_marker_calendar_artifacts  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Build marker allowable dates and +3-day table with +2 fallback.")
    )
    parser.add_argument(
        "--markers-dir",
        type=str,
        default=str(paths.DATA_RAW_DIR / "markers"),
        help="Marker CSV directory (default: data/raw/markers).",
    )
    parser.add_argument(
        "--tickers-dir",
        type=str,
        default=str(paths.DATA_TICKERS_DIR),
        help="Raw ticker CSV directory (default: data/raw/tickers).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    out = generate_marker_calendar_artifacts(
        markers_dir=Path(args.markers_dir),
        tickers_dir=Path(args.tickers_dir),
    )

    print(f"[marker_calendar] markers_dir={out.get('markers_dir')}")
    print(f"[marker_calendar] tickers_dir={out.get('tickers_dir')}")
    print(
        f"[marker_calendar] allowable_dates={int(out.get('allowable_count') or 0)} "
        f"warnings={int(out.get('warning_count') or 0)} "
        f"tuesday_issues={int(out.get('tuesday_issue_count') or 0)}"
    )
    print(f"[marker_calendar] dates_csv={out.get('dates_csv')}")
    print(f"[marker_calendar] three_days_csv={out.get('three_days_csv')}")
    print(f"[marker_calendar] warnings_txt={out.get('warnings_txt')}")

    issues = list(out.get("tuesday_issues") or [])
    if issues:
        print("[marker_calendar] Non-Tuesday marker dates detected:")
        for item in issues:
            print(
                "  - "
                f"file={item.get('marker_file')} "
                f"iso={item.get('iso_date') or '-'} "
                f"weekday={item.get('weekday')} "
                f"raw={item.get('raw_date')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
