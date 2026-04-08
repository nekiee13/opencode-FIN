from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def _bootstrap_sys_path() -> Path:
    here = Path(__file__).resolve()
    app_root = here.parents[1]
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    return app_root


APP_ROOT = _bootstrap_sys_path()

from src.config import paths  # noqa: E402
from src.ui.services.ann_feature_sources import collect_ann_feature_records  # noqa: E402
from src.ui.services.ann_feature_store import (  # noqa: E402
    initialize_ann_feature_store,
    load_ann_feature_store_summary,
    record_ingest_file,
    upsert_ann_feature_records,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest ANN input feature stores from TI/PP/SVL/TDA artifact directories."
        )
    )
    parser.add_argument(
        "--ti-dir",
        type=str,
        default=str(paths.OUT_I_CALC_TI_DIR),
        help="Directory containing TI snapshots (*.csv)",
    )
    parser.add_argument(
        "--pp-dir",
        type=str,
        default=str(paths.OUT_I_CALC_PP_DIR),
        help="Directory containing PP snapshots (*.csv)",
    )
    parser.add_argument(
        "--svl-dir",
        type=str,
        default=str(paths.OUT_I_CALC_SVL_DIR),
        help="Directory containing SVL metrics (SVL_METRICS_*.csv)",
    )
    parser.add_argument(
        "--tda-dir",
        type=str,
        default=str(paths.OUT_I_CALC_TDA_DIR),
        help="Directory containing TDA metrics (TDA_METRICS_*.csv)",
    )
    parser.add_argument(
        "--store-path",
        type=str,
        default=str(paths.OUT_I_CALC_DIR / "stores" / "ann_input_features.sqlite"),
        help="Target SQLite path for ANN input feature stores",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all discovered records even when prior ingest exists.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def _utc_batch_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    ti_dir = Path(args.ti_dir).resolve()
    pp_dir = Path(args.pp_dir).resolve()
    svl_dir = Path(args.svl_dir).resolve()
    tda_dir = Path(args.tda_dir).resolve()
    store_path = Path(args.store_path).resolve()

    initialize_ann_feature_store(store_path)

    source_records = collect_ann_feature_records(
        ti_dir=ti_dir,
        pp_dir=pp_dir,
        svl_dir=svl_dir,
        tda_dir=tda_dir,
    )
    batch_tag = _utc_batch_tag()

    ingest_out = upsert_ann_feature_records(
        store_path=store_path,
        records=source_records,
        source_batch=batch_tag,
    )

    file_family_counts: dict[tuple[str, str], int] = {}
    for item in source_records:
        file_path = str(item.get("source_file") or "")
        family = str(item.get("source_family") or "")
        if not file_path or not family:
            continue
        key = (file_path, family)
        file_family_counts[key] = int(file_family_counts.get(key, 0)) + 1

    for (file_path, family), rows in sorted(file_family_counts.items()):
        record_ingest_file(
            store_path=store_path,
            file_path=file_path,
            source_family=family,
            source_batch=batch_tag,
            rows_written=rows,
            status="ingested_force" if bool(args.force) else "ingested",
            note="source=ann_feature_stores_ingest",
        )

    summary = load_ann_feature_store_summary(store_path)
    print(f"[ann_feature_stores_ingest] store={store_path}")
    print(f"[ann_feature_stores_ingest] rows_written={ingest_out['rows_written']}")
    for family, payload in summary.get("families", {}).items():
        print(
            "[ann_feature_stores_ingest] "
            f"{family}: rows={payload.get('rows')} latest_as_of={payload.get('latest_as_of_date')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
