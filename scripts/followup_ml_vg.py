#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_sys_path() -> Path:
    this_file = Path(__file__).resolve()
    scripts_dir = this_file.parent
    app_root = scripts_dir.parent

    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    compat_dir = app_root / "compat"
    if compat_dir.exists() and str(compat_dir) not in sys.path:
        sys.path.insert(0, str(compat_dir))

    return app_root


APP_ROOT = _bootstrap_sys_path()


def _import_vg_store():
    mod_path = APP_ROOT / "src" / "followup_ml" / "vg_store.py"
    spec = importlib.util.spec_from_file_location("followup_ml_vg_store", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load vg_store module from {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vg_store = _import_vg_store()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="followup_ml_vg.py",
        description="Follow-up ML violet/green store utilities.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-db", help="Initialize ML_VG_tables sqlite schema")
    p_init.add_argument(
        "--db-path",
        type=str,
        default="",
        help="Optional explicit sqlite path override",
    )

    p_ingest = sub.add_parser(
        "ingest-round", help="Ingest one round artifacts into VG db"
    )
    p_ingest.add_argument(
        "--round-id", required=True, help="Round identifier, e.g. 26-1-11"
    )
    p_ingest.add_argument(
        "--db-path",
        type=str,
        default="",
        help="Optional explicit sqlite path override",
    )

    p_materialize = sub.add_parser(
        "materialize",
        help="Materialize violet/blue/green for one forecast date",
    )
    p_materialize.add_argument(
        "--forecast-date",
        required=True,
        help="Forecast date key in yyyy-mm-dd format",
    )
    p_materialize.add_argument(
        "--policy-name",
        type=str,
        default="",
        help="Optional transform policy name (default: active policy)",
    )
    p_materialize.add_argument(
        "--memory-tail",
        type=int,
        default=None,
        help="Optional memory tail override",
    )
    p_materialize.add_argument(
        "--bootstrap-enabled",
        action="store_true",
        help="Force bootstrap enabled",
    )
    p_materialize.add_argument(
        "--bootstrap-disabled",
        action="store_true",
        help="Force bootstrap disabled",
    )
    p_materialize.add_argument(
        "--bootstrap-score",
        type=float,
        default=None,
        help="Optional bootstrap score override",
    )
    p_materialize.add_argument(
        "--write-dir",
        type=str,
        default="",
        help="Optional output directory to write violet/blue/green CSV files",
    )
    p_materialize.add_argument(
        "--db-path",
        type=str,
        default="",
        help="Optional explicit sqlite path override",
    )
    return p


def _resolve_path_arg(path_text: str) -> Optional[Path]:
    txt = str(path_text or "").strip()
    if txt == "":
        return None
    return Path(txt).expanduser().resolve()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    db_path = _resolve_path_arg(getattr(args, "db_path", ""))

    if args.cmd == "init-db":
        conn = vg_store.connect_vg_db(db_path)
        try:
            vg_store.initialize_vg_db(conn)
            policy_id = vg_store.ensure_default_transform_policy(conn)
            conn.commit()
        finally:
            conn.close()
        print("[followup-ml-vg] DB initialized")
        print(f"  db_path={vg_store.resolve_vg_db_path(db_path)}")
        print(f"  policy_id={policy_id}")
        return 0

    if args.cmd == "ingest-round":
        result = vg_store.ingest_round_from_artifacts(
            str(args.round_id), db_path=db_path
        )
        print("[followup-ml-vg] Round ingested")
        print(f"  db_path={result['db_path']}")
        print(f"  round_id={result['round_id']}")
        print(f"  forecast_date={result['forecast_date']}")
        print(f"  rows_total={result['rows_total']}")
        print(f"  rows_scored={result['rows_scored']}")
        print(f"  rows_upserted={result['rows_upserted']}")
        return 0

    if args.cmd == "materialize":
        bootstrap_override = None
        if bool(args.bootstrap_enabled) and bool(args.bootstrap_disabled):
            raise ValueError("bootstrap flags are mutually exclusive")
        if bool(args.bootstrap_enabled):
            bootstrap_override = True
        elif bool(args.bootstrap_disabled):
            bootstrap_override = False

        result = vg_store.materialize_vbg_for_date(
            str(args.forecast_date),
            db_path=db_path,
            policy_name=str(args.policy_name)
            if str(args.policy_name).strip()
            else None,
            memory_tail=args.memory_tail,
            bootstrap_enabled=bootstrap_override,
            bootstrap_score=args.bootstrap_score,
        )
        print("[followup-ml-vg] Materialization complete")
        print(f"  db_path={vg_store.resolve_vg_db_path(db_path)}")
        print(f"  forecast_date={result['forecast_date']}")
        print(f"  policy={result['policy_name']} ({result['policy_mode']})")
        print(f"  memory_tail={result['memory_tail']}")
        print(f"  bootstrap_enabled={result['bootstrap_enabled']}")
        print(f"  bootstrap_score={result['bootstrap_score']}")

        write_dir = _resolve_path_arg(args.write_dir)
        if write_dir is not None:
            write_dir.mkdir(parents=True, exist_ok=True)
            stamp = str(result["forecast_date"])
            (write_dir / f"{stamp}_violet.csv").write_text(
                vg_store.format_matrix_csv(
                    result["violet"], result["models"], result["tickers"]
                ),
                encoding="utf-8",
            )
            (write_dir / f"{stamp}_blue.csv").write_text(
                vg_store.format_matrix_csv(
                    result["blue"], result["models"], result["tickers"]
                ),
                encoding="utf-8",
            )
            (write_dir / f"{stamp}_green.csv").write_text(
                vg_store.format_matrix_csv(
                    result["green"], result["models"], result["tickers"]
                ),
                encoding="utf-8",
            )
            (write_dir / f"{stamp}_meta.json").write_text(
                json.dumps(result, indent=2),
                encoding="utf-8",
            )
            print(f"  write_dir={write_dir}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
