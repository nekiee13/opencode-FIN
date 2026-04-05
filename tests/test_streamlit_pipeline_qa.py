from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.ui.services.pipeline_qa import evaluate_pipeline_state, write_pipeline_qa_log
from src.ui.services.run_registry import append_stage_result, create_run, finalize_run


def _seed_violet_score(db_path: Path, forecast_date: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS violet_scores (
                forecast_date TEXT,
                model TEXT,
                ticker TEXT,
                accuracy_pct REAL,
                score_status TEXT,
                source_round_id TEXT,
                source_partial_scores_path TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO violet_scores(
                forecast_date, model, ticker, accuracy_pct, score_status,
                source_round_id, source_partial_scores_path, created_at, updated_at
            ) VALUES (?, 'Torch', 'TNX', 95.0, 'scored', 'r1', 'x', 't', 't')
            """,
            (forecast_date,),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_materialized_rows(db_path: Path, forecast_date: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS materialized_scores (
                run_id INTEGER NOT NULL,
                forecast_date TEXT NOT NULL,
                table_name TEXT NOT NULL,
                model TEXT NOT NULL,
                ticker TEXT NOT NULL,
                score_value REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO materialized_scores(
                run_id, forecast_date, table_name, model, ticker, score_value, created_at
            ) VALUES (1, ?, 'violet', 'Torch', 'TNX', 95.0, 't')
            """,
            (forecast_date,),
        )
        conn.execute(
            """
            INSERT INTO materialized_scores(
                run_id, forecast_date, table_name, model, ticker, score_value, created_at
            ) VALUES (1, ?, 'green', 'Torch', 'TNX', 97.5, 't')
            """,
            (forecast_date,),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_successful_all_ticker_run(runs_root: Path, selected_date: str) -> str:
    run = create_run(
        selected_date=selected_date,
        selected_ticker="ALL",
        total_stages=18,
        root_dir=runs_root,
    )
    idx = 1
    for ticker in ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"):
        for stage_name in ("svl_export", "tda_export", "make_fh3_table"):
            append_stage_result(
                run_id=str(run["run_id"]),
                stage_index=idx,
                stage_name=stage_name,
                category="core",
                ticker=ticker,
                command=["python", stage_name],
                returncode=0,
                stdout="ok",
                stderr="",
                duration_seconds=0.1,
                root_dir=runs_root,
            )
            idx += 1
    finalize_run(str(run["run_id"]), root_dir=runs_root)
    return str(run["run_id"])


def _seed_partial_scores_for_date(scores_dir: Path, selected_date: str) -> None:
    scores_dir.mkdir(parents=True, exist_ok=True)
    path = scores_dir / "26-1-11_partial_scores.csv"
    path.write_text(
        "\n".join(
            [
                "round_id,ticker,model,forecast_date,expected_actual_date,lookup_actual_date,pred_value,actual_close,accuracy_pct,transformed_score,score_status,transform_status",
                f"26-1-11,TNX,Torch,{selected_date},{selected_date},{selected_date},1,1,95,95,scored,mapped",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _seed_fh3_full_table(
    fh3_dir: Path,
    forecast_date: str,
    tickers: tuple[str, ...] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL"),
) -> None:
    fh3_dir.mkdir(parents=True, exist_ok=True)
    tag = forecast_date.replace("-", "")
    path = fh3_dir / f"FH3_TABLE_FULL_{tag}.csv"
    lines = [
        "Ticker,FilePrefix,Last_Close_ASOF,Model_Used,Col_Used,FH_Date1,FH_Day1,FH_Date2,FH_Day2,FH_Date3,FH_Day3,Run_Mode,AsOf_Cutoff"
    ]
    for ticker in tickers:
        prefix = "GSPC" if ticker == "SPX" else ticker
        lines.append(
            f"{ticker},{prefix},1.0,DYNAMIX,DYNAMIX_Pred,{forecast_date},1.1,{forecast_date},1.2,{forecast_date},1.3,replay,2025-07-29"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_evaluate_pipeline_state_flags_violet_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    vg_db = tmp_path / "ML_VG_tables.sqlite"
    fh3_dir = tmp_path / "fh3"
    _seed_successful_all_ticker_run(runs_root, "2025-07-29")
    _seed_fh3_full_table(fh3_dir, "2025-07-30")

    report = evaluate_pipeline_state(
        selected_date="2025-07-29",
        runs_root=runs_root,
        vg_db_path=vg_db,
        fh3_dir=fh3_dir,
    )

    assert report["index_code"] == "QA_PARTIAL_SCORES_MISSING"
    assert report["target_forecast_date"] == "2025-07-30"
    assert report["fh3_has_all_tickers"] is True
    assert report["latest_run_status"] == "success"
    assert report["has_violet_rows"] is False


def test_evaluate_pipeline_state_flags_ingest_missing_when_scores_exist(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    vg_db = tmp_path / "ML_VG_tables.sqlite"
    scores_dir = tmp_path / "scores"
    fh3_dir = tmp_path / "fh3"
    _seed_successful_all_ticker_run(runs_root, "2025-07-29")
    _seed_fh3_full_table(fh3_dir, "2025-07-30")
    _seed_partial_scores_for_date(scores_dir, "2025-07-30")

    report = evaluate_pipeline_state(
        selected_date="2025-07-29",
        runs_root=runs_root,
        vg_db_path=vg_db,
        scores_dir=scores_dir,
        fh3_dir=fh3_dir,
    )

    assert report["index_code"] == "QA_VG_INGEST_MISSING"
    assert report["partial_scores_has_target_forecast_date"] is True


def test_evaluate_pipeline_state_ok_when_violet_exists(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    vg_db = tmp_path / "ML_VG_tables.sqlite"
    fh3_dir = tmp_path / "fh3"
    _seed_successful_all_ticker_run(runs_root, "2025-07-29")
    _seed_fh3_full_table(fh3_dir, "2025-07-30")
    _seed_violet_score(vg_db, "2025-07-30")
    _seed_materialized_rows(vg_db, "2025-07-30")

    report = evaluate_pipeline_state(
        selected_date="2025-07-29",
        runs_root=runs_root,
        vg_db_path=vg_db,
        fh3_dir=fh3_dir,
    )

    assert report["index_code"] == "QA_OK"
    assert report["violet_for_target_forecast_date"] is True


def test_evaluate_pipeline_state_flags_materialize_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    vg_db = tmp_path / "ML_VG_tables.sqlite"
    fh3_dir = tmp_path / "fh3"
    _seed_successful_all_ticker_run(runs_root, "2025-07-29")
    _seed_fh3_full_table(fh3_dir, "2025-07-30")
    _seed_violet_score(vg_db, "2025-07-30")

    report = evaluate_pipeline_state(
        selected_date="2025-07-29",
        runs_root=runs_root,
        vg_db_path=vg_db,
        fh3_dir=fh3_dir,
    )

    assert report["index_code"] == "QA_MATERIALIZE_MISSING"


def test_evaluate_pipeline_state_flags_fh3_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    fh3_dir = tmp_path / "fh3"
    _seed_successful_all_ticker_run(runs_root, "2025-07-29")

    report = evaluate_pipeline_state(
        selected_date="2025-07-29",
        runs_root=runs_root,
        vg_db_path=tmp_path / "ML_VG_tables.sqlite",
        fh3_dir=fh3_dir,
    )

    assert report["index_code"] == "QA_FH3_MISSING"


def test_evaluate_pipeline_state_flags_fh3_incomplete_coverage(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    fh3_dir = tmp_path / "fh3"
    _seed_successful_all_ticker_run(runs_root, "2025-07-29")
    _seed_fh3_full_table(fh3_dir, "2025-07-30", tickers=("AAPL",))

    report = evaluate_pipeline_state(
        selected_date="2025-07-29",
        runs_root=runs_root,
        vg_db_path=tmp_path / "ML_VG_tables.sqlite",
        fh3_dir=fh3_dir,
    )

    assert report["index_code"] == "QA_FH3_INCOMPLETE"
    assert report["fh3_ticker_count"] == 1


def test_write_pipeline_qa_log_persists_json(tmp_path: Path) -> None:
    report = {
        "selected_date": "2025-07-29",
        "index_code": "QA_VIOLET_MISSING",
        "latest_run_id": "RUN-TEST-001",
    }
    log_path = write_pipeline_qa_log(
        report=report,
        root_dir=tmp_path,
    )
    assert log_path.exists()
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["index_code"] == "QA_VIOLET_MISSING"
    assert payload["latest_run_id"] == "RUN-TEST-001"
