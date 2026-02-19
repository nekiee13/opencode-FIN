from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


def _make_bday_close(n: int = 80) -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-02", periods=n, freq="B")
    vals = 100.0 + np.linspace(0.0, 3.0, n)
    return pd.DataFrame({"Close": vals.astype(float)}, index=idx)


def test_predict_dynamix_worker_success_cpu_env(monkeypatch, tmp_path: Path) -> None:
    from src.models import dynamix as dx

    data = _make_bday_close(120)
    repo_path = tmp_path / "DynaMix-python"
    repo_path.mkdir(parents=True, exist_ok=True)

    seen: Dict[str, Any] = {}

    def _fake_run(cmd, capture_output, text, check, timeout, cwd, env):  # type: ignore[no-untyped-def]
        seen["cmd"] = cmd
        seen["env"] = env
        artifact_csv = Path(str(cmd[cmd.index("--artifact-csv") + 1]))

        out = pd.DataFrame(
            {
                "Date": pd.bdate_range("2026-01-05", periods=3, freq="B"),
                "DYNAMIX_Pred": [101.1, 101.4, 101.8],
            }
        )
        artifact_csv.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(artifact_csv, index=False, date_format="%Y-%m-%d")

        payload = {
            "protocol_version": 1,
            "ok": True,
            "artifact_csv": str(artifact_csv),
            "meta": {"model_name": "dynamix-3d-alrnn-v1.0", "device": "cpu"},
        }
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(dx.subprocess, "run", _fake_run)

    out = dx.predict_dynamix(
        data,
        ticker="TEST",
        fh=3,
        dynamix_repo_path=str(repo_path),
    )

    assert out is not None
    assert len(out) == 3
    assert "DYNAMIX_Pred" in out.columns
    assert "DYNAMIX_Lower" in out.columns
    assert "DYNAMIX_Upper" in out.columns

    env = seen["env"]
    assert env["CUDA_VISIBLE_DEVICES"] == ""
    assert env["FIN_DYNAMIX_FORCE_CPU"] == "1"
    assert env["FIN_DYNAMIX_REPO"] == str(repo_path)


def test_predict_dynamix_worker_failure_returns_none(
    monkeypatch, tmp_path: Path
) -> None:
    from src.models import dynamix as dx

    data = _make_bday_close(120)
    repo_path = tmp_path / "DynaMix-python"
    repo_path.mkdir(parents=True, exist_ok=True)

    def _fake_run(cmd, capture_output, text, check, timeout, cwd, env):  # type: ignore[no-untyped-def]
        payload = {
            "protocol_version": 1,
            "ok": False,
            "error": {"type": "RuntimeError", "message": "synthetic failure"},
        }
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=2,
            stdout=json.dumps(payload),
            stderr="traceback",
        )

    monkeypatch.setattr(dx.subprocess, "run", _fake_run)

    out = dx.predict_dynamix(
        data,
        ticker="TEST",
        fh=3,
        dynamix_repo_path=str(repo_path),
    )
    assert out is None


def test_facade_compute_forecasts_accepts_dynamix_only(monkeypatch) -> None:
    from src.models.facade import (
        ForecastArtifact,
        compute_forecasts,
        select_forecast_path,
    )
    import src.models.facade as facade

    data = _make_bday_close(100)
    fut_idx = pd.bdate_range(data.index[-1] + pd.offsets.BDay(1), periods=3, freq="B")
    pred_df = pd.DataFrame({"DYNAMIX_Pred": [1.0, 2.0, 3.0]}, index=fut_idx)

    art = ForecastArtifact(
        pred_df=pred_df,
        pred_col="DYNAMIX_Pred",
        model="DYNAMIX",
    )

    monkeypatch.setattr(facade, "run_dynamix", lambda *args, **kwargs: art)

    bundle = compute_forecasts(
        data,
        ticker="TEST",
        fh=3,
        enabled_models=["DYNAMIX"],
    )

    assert "DYNAMIX" in bundle.forecasts
    key, selected = select_forecast_path(bundle)
    assert key == "DYNAMIX"
    assert selected.model == "DYNAMIX"


def test_discover_repo_path_falls_back_when_config_path_missing(
    monkeypatch, tmp_path: Path
) -> None:
    from src.models import dynamix as dx

    repo_root_clone = tmp_path / "DynaMix-python"
    repo_root_clone.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dx.paths, "APP_ROOT", tmp_path)
    monkeypatch.setattr(
        dx,
        "_discover_str",
        lambda name, default: str(tmp_path / "vendor" / "DynaMix-python"),
    )
    monkeypatch.delenv("FIN_DYNAMIX_REPO", raising=False)

    resolved = dx._discover_dynamix_repo_path()
    assert resolved == repo_root_clone.resolve()


def test_discover_repo_path_scans_dynamix_named_dirs(
    monkeypatch, tmp_path: Path
) -> None:
    from src.models import dynamix as dx

    app_root = tmp_path / "app"
    app_root.mkdir(parents=True, exist_ok=True)

    candidate = app_root / "DynaMix-python-main"
    (candidate / "src" / "model").mkdir(parents=True, exist_ok=True)
    (candidate / "src" / "model" / "forecaster.py").write_text(
        "# marker", encoding="utf-8"
    )

    monkeypatch.setattr(dx.paths, "APP_ROOT", app_root)
    monkeypatch.setattr(dx, "_discover_str", lambda name, default: "")
    monkeypatch.delenv("FIN_DYNAMIX_REPO", raising=False)

    resolved = dx._discover_dynamix_repo_path()
    assert resolved == candidate.resolve()


def test_build_worker_env_preserves_existing_repo_when_candidate_missing(
    monkeypatch, tmp_path: Path
) -> None:
    from src.models import dynamix as dx

    monkeypatch.setenv("FIN_DYNAMIX_REPO", "F:/custom/DynaMix-python")

    env = dx._build_worker_env(tmp_path / "missing_repo")
    assert env["FIN_DYNAMIX_REPO"] == "F:/custom/DynaMix-python"


def test_discover_repo_path_reads_dotenv(monkeypatch, tmp_path: Path) -> None:
    from src.models import dynamix as dx

    app_root = tmp_path / "app"
    app_root.mkdir(parents=True, exist_ok=True)

    repo_dir = app_root / "my-dynamix-repo"
    (repo_dir / "src" / "model").mkdir(parents=True, exist_ok=True)
    (repo_dir / "src" / "model" / "forecaster.py").write_text(
        "# marker", encoding="utf-8"
    )

    (app_root / ".env").write_text(
        f"FIN_DYNAMIX_REPO={repo_dir}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(dx.paths, "APP_ROOT", app_root)
    monkeypatch.setattr(dx, "_discover_str", lambda name, default: "")
    monkeypatch.delenv("FIN_DYNAMIX_REPO", raising=False)

    resolved = dx._discover_dynamix_repo_path()
    assert resolved == repo_dir.resolve()
