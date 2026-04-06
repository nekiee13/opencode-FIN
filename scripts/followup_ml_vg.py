#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence
from uuid import uuid4


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

from src.config import paths


def _import_vg_store():
    mod_path = APP_ROOT / "src" / "followup_ml" / "vg_store.py"
    spec = importlib.util.spec_from_file_location("followup_ml_vg_store", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load vg_store module from {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vg_store = _import_vg_store()


def _new_trace_id(prefix: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid4().hex[:6]}"


def _count_violet_rows(db_path: Path, forecast_date: str) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM violet_scores WHERE forecast_date = ?",
            (str(forecast_date),),
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _partial_scores_summary(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "rows_total": 0,
            "forecast_dates": [],
            "score_status_counts": {},
        }
    forecast_dates: set[str] = set()
    status_counts: dict[str, int] = {}
    rows_total = 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows_total += 1
            date_value = str(row.get("forecast_date") or "").strip()
            if date_value:
                forecast_dates.add(date_value)
            status = str(row.get("score_status") or "").strip() or "<blank>"
            status_counts[status] = int(status_counts.get(status, 0)) + 1
    return {
        "rows_total": int(rows_total),
        "forecast_dates": sorted(forecast_dates),
        "score_status_counts": status_counts,
    }


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

    p_seed = sub.add_parser(
        "seed-green-dummy",
        help="Seed four dummy green snapshots for debug verification",
    )
    p_seed.add_argument(
        "--db-path",
        type=str,
        default="",
        help="Optional explicit sqlite path override",
    )
    p_seed.add_argument(
        "--policy-name",
        type=str,
        default="debug_seed_green_v1",
        help="Policy name attached to seeded materialization runs",
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
        trace_id = _new_trace_id("VG-INGEST")
        context_path = (
            paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR
            / str(args.round_id)
            / "round_context.json"
        ).resolve()
        scores_path = (
            paths.OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR
            / f"{str(args.round_id)}_partial_scores.csv"
        ).resolve()
        resolved_db_path = vg_store.resolve_vg_db_path(db_path)
        preflight_payload = {
            "command": "ingest-round",
            "round_id": str(args.round_id),
            "db_path": str(resolved_db_path),
            "context_path": str(context_path),
            "context_exists": bool(context_path.exists()),
            "partial_scores_path": str(scores_path),
            "partial_scores_exists": bool(scores_path.exists()),
        }
        preflight_payload.update(_partial_scores_summary(scores_path))
        preflight_log = vg_store.write_vg_debug_log(
            stage="ingest_preflight",
            payload=preflight_payload,
            trace_id=trace_id,
        )
        try:
            result = vg_store.ingest_round_from_artifacts(
                str(args.round_id), db_path=db_path
            )
            result_log = vg_store.write_vg_debug_log(
                stage="ingest_result",
                payload={
                    "command": "ingest-round",
                    "round_id": str(args.round_id),
                    "db_path": str(resolved_db_path),
                    **result,
                },
                trace_id=trace_id,
            )
        except Exception as exc:
            error_log = vg_store.write_vg_debug_log(
                stage="ingest_error",
                payload={
                    "command": "ingest-round",
                    "round_id": str(args.round_id),
                    "db_path": str(resolved_db_path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                trace_id=trace_id,
            )
            print(f"[followup-ml-vg] trace_id={trace_id}")
            print(f"  log_preflight={preflight_log}")
            print(f"  log_error={error_log}")
            raise
        print("[followup-ml-vg] Round ingested")
        print(f"  trace_id={trace_id}")
        print(f"  log_preflight={preflight_log}")
        print(f"  log_result={result_log}")
        print(f"  db_path={result['db_path']}")
        print(f"  round_id={result['round_id']}")
        print(f"  forecast_date={result['forecast_date']}")
        print(f"  rows_total={result['rows_total']}")
        print(f"  rows_scored={result['rows_scored']}")
        print(f"  rows_upserted={result['rows_upserted']}")
        return 0

    if args.cmd == "materialize":
        trace_id = _new_trace_id("VG-MAT")
        bootstrap_override = None
        if bool(args.bootstrap_enabled) and bool(args.bootstrap_disabled):
            raise ValueError("bootstrap flags are mutually exclusive")
        if bool(args.bootstrap_enabled):
            bootstrap_override = True
        elif bool(args.bootstrap_disabled):
            bootstrap_override = False

        resolved_db_path = vg_store.resolve_vg_db_path(db_path)
        preflight_log = vg_store.write_vg_debug_log(
            stage="materialize_preflight",
            payload={
                "command": "materialize",
                "forecast_date": str(args.forecast_date),
                "db_path": str(resolved_db_path),
                "policy_name": str(args.policy_name).strip() or None,
                "memory_tail": args.memory_tail,
                "bootstrap_enabled_override": bootstrap_override,
                "bootstrap_score": args.bootstrap_score,
                "violet_rows_for_forecast_date": _count_violet_rows(
                    resolved_db_path,
                    str(args.forecast_date),
                ),
            },
            trace_id=trace_id,
        )

        try:
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
            result_log = vg_store.write_vg_debug_log(
                stage="materialize_result",
                payload={
                    "command": "materialize",
                    "forecast_date": str(args.forecast_date),
                    "db_path": str(resolved_db_path),
                    "materialization_run_id": result.get("run_id"),
                    "policy_name": result.get("policy_name"),
                    "policy_mode": result.get("policy_mode"),
                    "memory_tail": result.get("memory_tail"),
                    "bootstrap_enabled": result.get("bootstrap_enabled"),
                    "bootstrap_score": result.get("bootstrap_score"),
                    "models_count": len(result.get("models", [])),
                    "tickers_count": len(result.get("tickers", [])),
                    "materialized_rows_written": result.get(
                        "materialized_rows_written"
                    ),
                },
                trace_id=trace_id,
            )
        except Exception as exc:
            error_log = vg_store.write_vg_debug_log(
                stage="materialize_error",
                payload={
                    "command": "materialize",
                    "forecast_date": str(args.forecast_date),
                    "db_path": str(resolved_db_path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                trace_id=trace_id,
            )
            print(f"[followup-ml-vg] trace_id={trace_id}")
            print(f"  log_preflight={preflight_log}")
            print(f"  log_error={error_log}")
            raise
        print("[followup-ml-vg] Materialization complete")
        print(f"  trace_id={trace_id}")
        print(f"  log_preflight={preflight_log}")
        print(f"  log_result={result_log}")
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

    if args.cmd == "seed-green-dummy":
        trace_id = _new_trace_id("VG-SEED")
        resolved_db_path = vg_store.resolve_vg_db_path(db_path)
        preflight_log = vg_store.write_vg_debug_log(
            stage="seed_green_preflight",
            payload={
                "command": "seed-green-dummy",
                "db_path": str(resolved_db_path),
                "policy_name": str(args.policy_name),
                "snapshots": [
                    {"forecast_date": "2000-01-03", "green_value": 99.1},
                    {"forecast_date": "2000-01-10", "green_value": 99.2},
                    {"forecast_date": "2000-01-17", "green_value": 99.3},
                    {"forecast_date": "2000-01-24", "green_value": 99.4},
                ],
            },
            trace_id=trace_id,
        )

        result = vg_store.seed_dummy_green_snapshots(
            db_path=db_path,
            policy_name=str(args.policy_name),
        )
        result_log = vg_store.write_vg_debug_log(
            stage="seed_green_result",
            payload={
                "command": "seed-green-dummy",
                **result,
            },
            trace_id=trace_id,
        )
        print("[followup-ml-vg] Dummy green snapshots seeded")
        print(f"  trace_id={trace_id}")
        print(f"  log_preflight={preflight_log}")
        print(f"  log_result={result_log}")
        print(f"  db_path={result['db_path']}")
        print(f"  policy_name={result['policy_name']}")
        print(f"  dates_seeded={','.join(result['dates_seeded'])}")
        print(f"  rows_per_date={result['rows_per_date']}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
