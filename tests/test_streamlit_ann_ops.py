from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.ui.services import ann_ops
from src.ui.services.ann_ops import load_ann_store_summary
from src.ui.services.ann_feature_store import (
    initialize_ann_feature_store,
    upsert_ann_feature_records,
)


def test_load_ann_store_summary_missing_store(tmp_path: Path) -> None:
    out = load_ann_store_summary(tmp_path / "missing.sqlite")
    assert out["exists"] is False
    assert out["families"]["ti"]["rows"] == 0


def test_load_ann_store_summary_reads_latest_date(tmp_path: Path) -> None:
    db_path = tmp_path / "ann_input_features.sqlite"
    initialize_ann_feature_store(db_path)
    upsert_ann_feature_records(
        store_path=db_path,
        source_batch="20260331",
        records=[
            {
                "as_of_date": "2026-03-31",
                "ticker": "TNX",
                "feature_name": "RSI (14)",
                "feature_value": 54.3,
                "source_family": "ti",
                "source_file": "/tmp/TI/TNX.csv",
                "value_status": "present",
            },
            {
                "as_of_date": "2026-03-24",
                "ticker": "TNX",
                "feature_name": "H1_Entropy",
                "feature_value": 2.014,
                "source_family": "tda_h1",
                "source_file": "/tmp/tda/TDA_METRICS_20260324.csv",
                "value_status": "present",
            },
        ],
    )

    out = load_ann_store_summary(db_path)
    assert out["exists"] is True
    assert out["families"]["ti"]["rows"] == 1
    assert out["families"]["ti"]["latest_as_of_date"] == "2026-03-31"
    assert out["families"]["tda_h1"]["rows"] == 1


def test_run_ann_feature_stores_ingest_builds_cli_command(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(cmd, cwd, text, capture_output, check):
        captured["cmd"] = list(cmd)
        captured["cwd"] = str(cwd)
        _ = text, capture_output, check
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(ann_ops.subprocess, "run", _fake_run)

    out = ann_ops.run_ann_feature_stores_ingest(
        ti_dir=Path("/tmp/TI"),
        pp_dir=Path("/tmp/PP"),
        svl_dir=Path("/tmp/svl"),
        tda_dir=Path("/tmp/tda"),
        store_path=Path("/tmp/ann_input_features.sqlite"),
        force=True,
    )

    assert out["returncode"] == 0
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert any(str(x).endswith("ann_feature_stores_ingest.py") for x in cmd)
    assert "--ti-dir" in cmd
    assert "--pp-dir" in cmd
    assert "--svl-dir" in cmd
    assert "--tda-dir" in cmd
    assert "--store-path" in cmd
    assert "--force" in cmd


def test_run_ann_train_builds_cli_command(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(cmd, cwd, text, capture_output, check):
        captured["cmd"] = list(cmd)
        captured["cwd"] = str(cwd)
        _ = text, capture_output, check
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(ann_ops.subprocess, "run", _fake_run)

    out = ann_ops.run_ann_train(
        tickers=["TNX", "SPX"],
        window_length=4,
        lag_depth=2,
        train_end_date="2026-03-31",
        target_mode="sgn",
    )
    assert out["returncode"] == 0
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert any(str(x).endswith("ann_train.py") for x in cmd)
    assert "--tickers" in cmd
    assert "TNX" in cmd
    assert "SPX" in cmd
    assert "--window-length" in cmd
    assert "--lag-depth" in cmd
    assert "--train-end-date" in cmd
    assert "2026-03-31" in cmd
    assert "--target-mode" in cmd
    assert "sgn" in cmd


def test_run_ann_tune_builds_cli_command(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(cmd, cwd, text, capture_output, check):
        captured["cmd"] = list(cmd)
        captured["cwd"] = str(cwd)
        _ = text, capture_output, check
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(ann_ops.subprocess, "run", _fake_run)

    out = ann_ops.run_ann_tune(max_trials=12)
    assert out["returncode"] == 0
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert any(str(x).endswith("ann_tune.py") for x in cmd)
    assert "--max-trials" in cmd
