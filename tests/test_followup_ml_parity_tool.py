from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_parity_module(repo_root: Path):
    script_path = repo_root / "scripts" / "followup_ml_parity.py"
    spec = importlib.util.spec_from_file_location("followup_ml_parity", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _prepare_min_round_artifacts(round_id: str, base_out: Path) -> None:
    rounds_dir = base_out / "rounds" / round_id
    _write(
        rounds_dir / "round_context.json",
        json.dumps(
            {
                "round_id": round_id,
                "round_state": "DRAFT_T0",
                "generated_at": "2026-02-28 00:00:00",
                "outputs": {},
            }
        ),
    )
    _write(rounds_dir / "t0_forecasts.csv", "ticker,model,pred_value\nTNX,Torch,4.07\n")
    _write(rounds_dir / "t0_draft_metrics.csv", "ticker,available_models\nTNX,1\n")
    _write(rounds_dir / "t0_day3_matrix.csv", "ticker,Torch\nTNX,4.07\n")


def test_parity_snapshot_and_compare_pass(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    mod = _load_parity_module(repo_root)

    out_root = tmp_path / "out" / "followup_ml"
    fixture_root = tmp_path / "fixtures" / "parity"
    round_id = "26-1-09"

    # Redirect canonical paths used by parity tool.
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR", out_root / "rounds")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR", out_root / "scores")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_AVR_DIR", out_root / "avr")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_WEIGHTS_DIR", out_root / "weights")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR", out_root / "dashboard")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_DIR", out_root)

    _prepare_min_round_artifacts(round_id, out_root)

    rc = mod.snapshot_round(round_id, fixture_root)
    assert rc == 0
    assert (fixture_root / round_id / "round_context.json").exists()

    rc2 = mod.compare_round(round_id, fixture_root, 1e-6)
    assert rc2 == 0
    assert (out_root / "reports" / f"parity_{round_id}.md").exists()


def test_parity_compare_detects_numeric_drift(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    mod = _load_parity_module(repo_root)

    out_root = tmp_path / "out" / "followup_ml"
    fixture_root = tmp_path / "fixtures" / "parity"
    round_id = "26-1-11"

    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR", out_root / "rounds")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR", out_root / "scores")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_AVR_DIR", out_root / "avr")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_WEIGHTS_DIR", out_root / "weights")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_DASHBOARD_DIR", out_root / "dashboard")
    monkeypatch.setattr(mod.paths, "OUT_I_CALC_FOLLOWUP_ML_DIR", out_root)

    _prepare_min_round_artifacts(round_id, out_root)
    assert mod.snapshot_round(round_id, fixture_root) == 0

    # Introduce numeric drift in actual artifact after fixture capture.
    _write(out_root / "rounds" / round_id / "t0_day3_matrix.csv", "ticker,Torch\nTNX,9.99\n")

    rc = mod.compare_round(round_id, fixture_root, 1e-6)
    assert rc == 1
