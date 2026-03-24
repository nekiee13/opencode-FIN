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


def _import_llm_vg_store():
    mod_path = APP_ROOT / "src" / "followup_ml" / "llm_vg_store.py"
    spec = importlib.util.spec_from_file_location("followup_llm_vg_store", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load llm_vg_store module from {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


llm_vg_store = _import_llm_vg_store()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="followup_llm_vg.py",
        description="Follow-up LLM violet/blue/green and marker DB utilities.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-db", help="Initialize LLM VG sqlite schema")
    p_init.add_argument(
        "--llm-db-path",
        type=str,
        default="",
        help="Optional explicit LLM sqlite path override",
    )

    p_mark_init = sub.add_parser(
        "init-markers-db", help="Initialize marker comparison sqlite schema"
    )
    p_mark_init.add_argument(
        "--markers-db-path",
        type=str,
        default="",
        help="Optional explicit markers sqlite path override",
    )

    p_alias = sub.add_parser("seed-aliases", help="Seed default model alias rules")
    p_alias.add_argument(
        "--llm-db-path",
        type=str,
        default="",
        help="Optional explicit LLM sqlite path override",
    )

    p_ingest_models = sub.add_parser(
        "ingest-model-table",
        help="Ingest LLM model markdown table into LLM_VG_tables",
    )
    p_ingest_models.add_argument("--forecast-date", required=True, help="yyyy-mm-dd")
    p_ingest_models.add_argument(
        "--round-id",
        default="",
        help="Optional round identifier; defaults to forecast-date",
    )
    p_ingest_models.add_argument(
        "--table-file",
        required=True,
        help="Path to markdown table file containing LLM model rows",
    )
    p_ingest_models.add_argument(
        "--llm-db-path",
        type=str,
        default="",
        help="Optional explicit LLM sqlite path override",
    )

    p_ingest_markers = sub.add_parser(
        "ingest-markers-table",
        help="Ingest marker markdown table into Markers sqlite",
    )
    p_ingest_markers.add_argument("--forecast-date", required=True, help="yyyy-mm-dd")
    p_ingest_markers.add_argument(
        "--table-file",
        required=True,
        help="Path to markdown table file containing marker rows",
    )
    p_ingest_markers.add_argument(
        "--markers-db-path",
        type=str,
        default="",
        help="Optional explicit markers sqlite path override",
    )

    p_mat = sub.add_parser(
        "materialize",
        help="Materialize LLM violet/blue/green from predictions and marker close-real",
    )
    p_mat.add_argument("--forecast-date", required=True, help="yyyy-mm-dd")
    p_mat.add_argument(
        "--policy-name",
        type=str,
        default="",
        help="Optional transform policy name",
    )
    p_mat.add_argument(
        "--memory-tail",
        type=int,
        default=None,
        help="Optional memory tail override",
    )
    p_mat.add_argument(
        "--bootstrap-enabled",
        action="store_true",
        help="Force bootstrap enabled",
    )
    p_mat.add_argument(
        "--bootstrap-disabled",
        action="store_true",
        help="Force bootstrap disabled",
    )
    p_mat.add_argument(
        "--bootstrap-score",
        type=float,
        default=None,
        help="Optional bootstrap score override",
    )
    p_mat.add_argument(
        "--marker-name",
        type=str,
        default=llm_vg_store.MARKER_CLOSE_REAL_TPLUS3,
        help="Marker name used for accuracy scoring",
    )
    p_mat.add_argument(
        "--llm-db-path",
        type=str,
        default="",
        help="Optional explicit LLM sqlite path override",
    )
    p_mat.add_argument(
        "--markers-db-path",
        type=str,
        default="",
        help="Optional explicit markers sqlite path override",
    )
    p_mat.add_argument(
        "--write-dir",
        type=str,
        default="",
        help="Optional output directory for exported matrices and metadata",
    )
    return p


def _resolve_path_arg(path_text: str) -> Optional[Path]:
    txt = str(path_text or "").strip()
    if txt == "":
        return None
    return Path(txt).expanduser().resolve()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    llm_db_path = _resolve_path_arg(getattr(args, "llm_db_path", ""))
    markers_db_path = _resolve_path_arg(getattr(args, "markers_db_path", ""))

    if args.cmd == "init-db":
        conn = llm_vg_store.connect_llm_vg_db(llm_db_path)
        try:
            llm_vg_store.initialize_llm_vg_db(conn)
            pid = llm_vg_store.ensure_default_transform_policy(conn)
            seeded = llm_vg_store.seed_default_aliases(conn)
            conn.commit()
        finally:
            conn.close()
        print("[followup-llm-vg] LLM DB initialized")
        print(f"  db_path={llm_vg_store.resolve_llm_vg_db_path(llm_db_path)}")
        print(f"  policy_id={pid}")
        print(f"  aliases_seeded={seeded}")
        return 0

    if args.cmd == "init-markers-db":
        conn = llm_vg_store.connect_markers_db(markers_db_path)
        try:
            llm_vg_store.initialize_markers_db(conn)
            conn.commit()
        finally:
            conn.close()
        print("[followup-llm-vg] Markers DB initialized")
        print(f"  db_path={llm_vg_store.resolve_markers_db_path(markers_db_path)}")
        return 0

    if args.cmd == "seed-aliases":
        conn = llm_vg_store.connect_llm_vg_db(llm_db_path)
        try:
            llm_vg_store.initialize_llm_vg_db(conn)
            seeded = llm_vg_store.seed_default_aliases(conn)
            conn.commit()
        finally:
            conn.close()
        print("[followup-llm-vg] Alias rules seeded")
        print(f"  db_path={llm_vg_store.resolve_llm_vg_db_path(llm_db_path)}")
        print(f"  aliases_seeded={seeded}")
        return 0

    if args.cmd == "ingest-model-table":
        table_file = Path(str(args.table_file)).expanduser().resolve()
        round_id = str(args.round_id).strip() or str(args.forecast_date).strip()
        result = llm_vg_store.ingest_llm_model_table_from_markdown(
            forecast_date=str(args.forecast_date),
            round_id=round_id,
            markdown_path=table_file,
            llm_db_path=llm_db_path,
        )
        print("[followup-llm-vg] Model table ingested")
        print(f"  db_path={result['db_path']}")
        print(f"  forecast_date={result['forecast_date']}")
        print(f"  round_id={result['round_id']}")
        print(f"  models_total={result['models_total']}")
        print(f"  rows_upserted={result['rows_upserted']}")
        unresolved = result.get("unresolved_model_labels", [])
        if unresolved:
            print(f"  unresolved_labels={len(unresolved)}")
            for label in unresolved:
                print(f"    - {label}")
        return 0

    if args.cmd == "ingest-markers-table":
        table_file = Path(str(args.table_file)).expanduser().resolve()
        result = llm_vg_store.ingest_markers_from_markdown(
            forecast_date=str(args.forecast_date),
            markdown_path=table_file,
            markers_db_path=markers_db_path,
        )
        print("[followup-llm-vg] Markers table ingested")
        print(f"  db_path={result['db_path']}")
        print(f"  forecast_date={result['forecast_date']}")
        print(f"  marker_rows={result['marker_rows']}")
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

        result = llm_vg_store.materialize_llm_vbg_for_date(
            str(args.forecast_date),
            llm_db_path=llm_db_path,
            markers_db_path=markers_db_path,
            policy_name=str(args.policy_name).strip() or None,
            memory_tail=args.memory_tail,
            bootstrap_enabled=bootstrap_override,
            bootstrap_score=args.bootstrap_score,
            marker_name_for_scoring=str(args.marker_name),
        )
        print("[followup-llm-vg] Materialization complete")
        print(f"  llm_db_path={llm_vg_store.resolve_llm_vg_db_path(llm_db_path)}")
        print(
            f"  markers_db_path={llm_vg_store.resolve_markers_db_path(markers_db_path)}"
        )
        print(f"  forecast_date={result['forecast_date']}")
        print(f"  marker_name={result['marker_name']}")
        print(f"  policy={result['policy_name']} ({result['policy_mode']})")
        print(f"  memory_tail={result['memory_tail']}")
        print(f"  bootstrap_enabled={result['bootstrap_enabled']}")
        print(f"  bootstrap_score={result['bootstrap_score']}")

        write_dir = _resolve_path_arg(str(args.write_dir))
        if write_dir is not None:
            write_dir.mkdir(parents=True, exist_ok=True)
            stamp = str(result["forecast_date"])
            (write_dir / f"{stamp}_predicted.csv").write_text(
                llm_vg_store.format_matrix_csv(
                    result["predicted"], result["models"], result["tickers"]
                ),
                encoding="utf-8",
            )
            (write_dir / f"{stamp}_violet.csv").write_text(
                llm_vg_store.format_matrix_csv(
                    result["violet"], result["models"], result["tickers"]
                ),
                encoding="utf-8",
            )
            (write_dir / f"{stamp}_blue.csv").write_text(
                llm_vg_store.format_matrix_csv(
                    result["blue"], result["models"], result["tickers"]
                ),
                encoding="utf-8",
            )
            (write_dir / f"{stamp}_green.csv").write_text(
                llm_vg_store.format_matrix_csv(
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
