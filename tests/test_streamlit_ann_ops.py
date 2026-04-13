from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.ui.services import ann_ops
from src.ui.services.ann_ops import (
    extract_ann_train_run_dir,
    load_ann_store_summary,
    load_ann_train_artifacts,
)
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
        epochs=777,
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
    assert "--epochs" in cmd
    assert "777" in cmd
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


def test_run_ann_train_builds_prune_cli_flags(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _fake_run(cmd, cwd, text, capture_output, check):
        captured["cmd"] = list(cmd)
        captured["cwd"] = str(cwd)
        _ = text, capture_output, check
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(ann_ops.subprocess, "run", _fake_run)

    allowlist_path = tmp_path / "pruned_inputs.json"
    save_path = tmp_path / "saved_inputs.json"
    out = ann_ops.run_ann_train(
        tickers=["TNX"],
        feature_selection="importance",
        importance_keep_ratio=0.4,
        feature_allowlist_file=allowlist_path,
        save_selected_features_file=save_path,
    )

    assert out["returncode"] == 0
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert "--feature-selection" in cmd
    assert "importance" in cmd
    assert "--importance-keep-ratio" in cmd
    assert "0.4" in cmd
    assert "--feature-allowlist-file" in cmd
    assert str(allowlist_path) in cmd
    assert "--save-selected-features-file" in cmd
    assert str(save_path) in cmd


def test_extract_ann_train_run_dir_and_load_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20260408-223618"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(
        '{"rows": 42, "features_after_selection": 230}',
        encoding="utf-8",
    )
    (run_dir / "top_feature_impacts.json").write_text(
        '[{"rank":1,"feature":"ti::RSI (14)__lag0","impact_score":0.81}]',
        encoding="utf-8",
    )

    stdout = f"[ann_train] run_dir={run_dir}\n[ann_train] rows=42\n"
    parsed = extract_ann_train_run_dir(stdout)
    assert parsed == run_dir

    out = load_ann_train_artifacts(run_dir)
    assert isinstance(out["summary"], dict)
    assert out["summary"]["rows"] == 42
    assert isinstance(out["top_feature_impacts"], list)
    assert out["top_feature_impacts"][0]["rank"] == 1
