from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from src.config import paths


def _load_vg_store_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "src" / "followup_ml" / "vg_store.py"
    spec = importlib.util.spec_from_file_location("followup_ml_vg_store", mod_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vg_store = _load_vg_store_module()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _prepare_round(
    *,
    rounds_dir: Path,
    scores_dir: Path,
    round_id: str,
    forecast_date: str,
    accuracy_torch_tnx: float,
) -> None:
    context = {
        "round_id": round_id,
        "round_state": "FINAL_TPLUS3",
        "generated_at": "2026-03-01 10:00:00",
        "finalized_at": "2026-03-01 10:05:00",
        "run_mode": "strict_production",
        "actuals": {
            "lookup_date_override": "",
        },
    }
    _write(rounds_dir / round_id / "round_context.json", json.dumps(context, indent=2))

    csv_text = "\n".join(
        [
            "round_id,ticker,model,forecast_date,expected_actual_date,lookup_actual_date,pred_value,actual_close,accuracy_pct,transformed_score,score_status,transform_status",
            f"{round_id},TNX,Torch,{forecast_date},{forecast_date},{forecast_date},1,1,{accuracy_torch_tnx},99,scored,mapped",
            f"{round_id},DJI,Torch,{forecast_date},{forecast_date},{forecast_date},1,1,98,98,scored,mapped",
            f"{round_id},TNX,ARIMAX,{forecast_date},{forecast_date},{forecast_date},1,1,95,95,scored,mapped",
            f"{round_id},DJI,ARIMAX,{forecast_date},{forecast_date},{forecast_date},,1,,,model_unavailable,model_unavailable",
            "",
        ]
    )
    _write(scores_dir / f"{round_id}_partial_scores.csv", csv_text)


def test_ingest_round_creates_db_and_rows(tmp_path, monkeypatch) -> None:
    rounds_dir = tmp_path / "out" / "followup_ml" / "rounds"
    scores_dir = tmp_path / "out" / "followup_ml" / "scores"
    db_path = tmp_path / "out" / "i_calc" / "ML" / "ML_VG_tables.sqlite"

    mapping_path = tmp_path / "config" / "followup_ml_value_assign.csv"
    _write(mapping_path, "value,assign\n0,0\n99,99\n99.99,100\n")

    monkeypatch.setenv("FIN_ML_VG_DB", str(db_path))
    monkeypatch.setattr(paths, "OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR", rounds_dir)
    monkeypatch.setattr(paths, "OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR", scores_dir)
    monkeypatch.setattr(paths, "FOLLOWUP_ML_VALUE_ASSIGN_PATH", mapping_path)

    _prepare_round(
        rounds_dir=rounds_dir,
        scores_dir=scores_dir,
        round_id="26-1-99",
        forecast_date="2026-03-10",
        accuracy_torch_tnx=99.4,
    )

    result = vg_store.ingest_round_from_artifacts("26-1-99")
    assert result["forecast_date"] == "2026-03-10"
    assert result["rows_total"] == 4
    assert result["rows_upserted"] == 4
    assert db_path.exists()

    conn = vg_store.connect_vg_db(db_path)
    try:
        rounds = conn.execute("SELECT COUNT(*) AS c FROM rounds").fetchone()
        violet = conn.execute("SELECT COUNT(*) AS c FROM violet_scores").fetchone()
        assert rounds is not None and int(rounds["c"]) == 1
        assert violet is not None and int(violet["c"]) == 4
    finally:
        conn.close()


def test_materialize_uses_bootstrap_padding(tmp_path, monkeypatch) -> None:
    rounds_dir = tmp_path / "out" / "followup_ml" / "rounds"
    scores_dir = tmp_path / "out" / "followup_ml" / "scores"
    db_path = tmp_path / "out" / "i_calc" / "ML" / "ML_VG_tables.sqlite"

    mapping_path = tmp_path / "config" / "followup_ml_value_assign.csv"
    _write(mapping_path, "value,assign\n0,0\n90,90\n95,95\n99,99\n99.99,100\n")

    monkeypatch.setenv("FIN_ML_VG_DB", str(db_path))
    monkeypatch.setattr(paths, "OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR", rounds_dir)
    monkeypatch.setattr(paths, "OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR", scores_dir)
    monkeypatch.setattr(paths, "FOLLOWUP_ML_VALUE_ASSIGN_PATH", mapping_path)

    _prepare_round(
        rounds_dir=rounds_dir,
        scores_dir=scores_dir,
        round_id="26-1-01",
        forecast_date="2026-03-03",
        accuracy_torch_tnx=95.0,
    )
    _prepare_round(
        rounds_dir=rounds_dir,
        scores_dir=scores_dir,
        round_id="26-1-02",
        forecast_date="2026-03-10",
        accuracy_torch_tnx=99.4,
    )

    vg_store.ingest_round_from_artifacts("26-1-01")
    vg_store.ingest_round_from_artifacts("26-1-02")

    out = vg_store.materialize_vbg_for_date(
        "2026-03-10",
        memory_tail=4,
        bootstrap_enabled=True,
        bootstrap_score=99.0,
    )

    # Blue: default policy applies step-floor mapping over value_assign anchors.
    got_blue = out["blue"]["Torch"]["TNX"]
    assert got_blue is not None
    assert abs(float(got_blue) - 99.0) < 1e-9
    assert out["policy_mode"] == "step_floor"

    # Green uses one prior transformed value (95) + three bootstrap slots (99).
    expected_green = (95.0 + 99.0 + 99.0 + 99.0) / 4.0
    got_green = out["green"]["Torch"]["TNX"]
    assert got_green is not None
    assert abs(float(got_green) - expected_green) < 1e-9

    meta = out["green_meta"]["Torch"]["TNX"]
    assert meta["real_rounds_used"] == 1
    assert meta["bootstrap_slots_used"] == 3

    conn = vg_store.connect_vg_db(db_path)
    try:
        tbl = conn.execute(
            "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name='materialized_scores'"
        ).fetchone()
        assert tbl is not None and int(tbl["c"]) == 1

        rows = conn.execute(
            """
            SELECT table_name, COUNT(*) AS c
            FROM materialized_scores
            WHERE forecast_date = '2026-03-10'
            GROUP BY table_name
            ORDER BY table_name
            """
        ).fetchall()
        got = {str(r["table_name"]): int(r["c"]) for r in rows}
        # 2 models x 2 tickers from fixture rows are persisted for violet + green.
        assert got == {"green": 4, "violet": 4}
    finally:
        conn.close()


def test_warmup_slots_follow_real_data_start_boundary(tmp_path, monkeypatch) -> None:
    rounds_dir = tmp_path / "out" / "followup_ml" / "rounds"
    scores_dir = tmp_path / "out" / "followup_ml" / "scores"
    db_path = tmp_path / "out" / "i_calc" / "ML" / "ML_VG_tables.sqlite"

    mapping_path = tmp_path / "config" / "followup_ml_value_assign.csv"
    _write(mapping_path, "value,assign\n0,0\n90,90\n95,95\n99,99\n99.99,100\n")

    monkeypatch.setenv("FIN_ML_VG_DB", str(db_path))
    monkeypatch.setattr(paths, "OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR", rounds_dir)
    monkeypatch.setattr(paths, "OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR", scores_dir)
    monkeypatch.setattr(paths, "FOLLOWUP_ML_VALUE_ASSIGN_PATH", mapping_path)

    _prepare_round(
        rounds_dir=rounds_dir,
        scores_dir=scores_dir,
        round_id="25-0-01",
        forecast_date="2025-07-29",
        accuracy_torch_tnx=95.0,
    )
    _prepare_round(
        rounds_dir=rounds_dir,
        scores_dir=scores_dir,
        round_id="25-0-02",
        forecast_date="2025-08-05",
        accuracy_torch_tnx=95.0,
    )

    vg_store.ingest_round_from_artifacts("25-0-01")
    vg_store.ingest_round_from_artifacts("25-0-02")

    out_jul = vg_store.materialize_vbg_for_date(
        "2025-07-29",
        memory_tail=4,
        bootstrap_enabled=True,
        bootstrap_score=99.0,
    )
    meta_jul = out_jul["green_meta"]["Torch"]["TNX"]
    assert meta_jul["real_rounds_used"] == 0
    assert meta_jul["bootstrap_slots_used"] == 4

    out_aug = vg_store.materialize_vbg_for_date(
        "2025-08-05",
        memory_tail=4,
        bootstrap_enabled=True,
        bootstrap_score=99.0,
    )
    meta_aug = out_aug["green_meta"]["Torch"]["TNX"]
    assert meta_aug["real_rounds_used"] == 1
    assert meta_aug["bootstrap_slots_used"] == 3
    assert out_aug["real_data_start_date"] == "2025-07-29"


def test_piecewise_linear_policy_materialization(tmp_path, monkeypatch) -> None:
    rounds_dir = tmp_path / "out" / "followup_ml" / "rounds"
    scores_dir = tmp_path / "out" / "followup_ml" / "scores"
    db_path = tmp_path / "out" / "i_calc" / "ML" / "ML_VG_tables.sqlite"

    mapping_path = tmp_path / "config" / "followup_ml_value_assign.csv"
    _write(mapping_path, "value,assign\n0,0\n100,100\n")

    monkeypatch.setenv("FIN_ML_VG_DB", str(db_path))
    monkeypatch.setattr(paths, "OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR", rounds_dir)
    monkeypatch.setattr(paths, "OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR", scores_dir)
    monkeypatch.setattr(paths, "FOLLOWUP_ML_VALUE_ASSIGN_PATH", mapping_path)

    _prepare_round(
        rounds_dir=rounds_dir,
        scores_dir=scores_dir,
        round_id="26-1-77",
        forecast_date="2026-03-17",
        accuracy_torch_tnx=50.0,
    )
    vg_store.ingest_round_from_artifacts("26-1-77")

    conn = vg_store.connect_vg_db(db_path)
    try:
        vg_store.initialize_vg_db(conn)
        vg_store.upsert_transform_policy(
            conn,
            policy_name="linear_test",
            mode="piecewise_linear",
            points=[(0.0, 0.0), (100.0, 200.0)],
            set_active=False,
        )
        conn.commit()
    finally:
        conn.close()

    out = vg_store.materialize_vbg_for_date(
        "2026-03-17",
        policy_name="linear_test",
        memory_tail=3,
        bootstrap_enabled=False,
    )
    got = out["blue"]["Torch"]["TNX"]
    assert got is not None
    assert abs(float(got) - 100.0) < 1e-9


def test_seed_dummy_green_snapshots_creates_four_dates(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "out" / "i_calc" / "ML" / "ML_VG_tables.sqlite"
    mapping_path = tmp_path / "config" / "followup_ml_value_assign.csv"
    _write(mapping_path, "value,assign\n0,0\n99.99,100\n")

    monkeypatch.setenv("FIN_ML_VG_DB", str(db_path))
    monkeypatch.setattr(paths, "FOLLOWUP_ML_VALUE_ASSIGN_PATH", mapping_path)

    result = vg_store.seed_dummy_green_snapshots(db_path=db_path)
    assert result["dates_seeded"] == [
        "2000-01-03",
        "2000-01-10",
        "2000-01-17",
        "2000-01-24",
    ]
    assert result["rows_per_date"] == 54

    conn = vg_store.connect_vg_db(db_path)
    try:
        run_rows = conn.execute(
            """
            SELECT forecast_date, COUNT(*)
            FROM materialization_runs
            GROUP BY forecast_date
            ORDER BY forecast_date
            """
        ).fetchall()
        assert [(str(r[0]), int(r[1])) for r in run_rows] == [
            ("2000-01-03", 1),
            ("2000-01-10", 1),
            ("2000-01-17", 1),
            ("2000-01-24", 1),
        ]

        score_rows = conn.execute(
            """
            SELECT forecast_date, table_name, COUNT(*)
            FROM materialized_scores
            GROUP BY forecast_date, table_name
            ORDER BY forecast_date, table_name
            """
        ).fetchall()
        assert [(str(r[0]), str(r[1]), int(r[2])) for r in score_rows] == [
            ("2000-01-03", "green", 54),
            ("2000-01-10", "green", 54),
            ("2000-01-17", "green", 54),
            ("2000-01-24", "green", 54),
        ]

        values = conn.execute(
            """
            SELECT forecast_date, MIN(score_value), MAX(score_value)
            FROM materialized_scores
            WHERE table_name = 'green'
            GROUP BY forecast_date
            ORDER BY forecast_date
            """
        ).fetchall()
        assert [(str(r[0]), float(r[1]), float(r[2])) for r in values] == [
            ("2000-01-03", 99.1, 99.1),
            ("2000-01-10", 99.2, 99.2),
            ("2000-01-17", 99.3, 99.3),
            ("2000-01-24", 99.4, 99.4),
        ]
    finally:
        conn.close()


def test_write_vg_debug_log_persists_json(tmp_path) -> None:
    out = vg_store.write_vg_debug_log(
        stage="ingest_preflight",
        payload={"round_id": "26-1-11", "db_path": "x"},
        root_dir=tmp_path,
        trace_id="TRACE-TEST-001",
    )
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["trace_id"] == "TRACE-TEST-001"
    assert payload["stage"] == "ingest_preflight"
    assert payload["round_id"] == "26-1-11"
