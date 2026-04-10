from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from src.config import paths


def _selected_tickers(selected_ticker: str, tickers: Sequence[str]) -> list[str]:
    value = str(selected_ticker or "").strip().upper()
    if value in {"", "ALL", "ALL_TICKERS"}:
        return [str(x).strip().upper() for x in tickers if str(x).strip()]
    return [value]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _latest_tune_run(tuning_dir: Path) -> tuple[str | None, Path | None]:
    if not tuning_dir.exists():
        return None, None
    candidates = sorted(
        [x for x in tuning_dir.iterdir() if x.is_dir() and x.name.startswith("tune_")],
        key=lambda x: x.name,
        reverse=True,
    )
    if not candidates:
        return None, None
    latest = candidates[0]
    return str(latest.name), latest


def _setup_summary(payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    training = (
        payload.get("training") if isinstance(payload.get("training"), dict) else {}
    )
    evaluation = (
        payload.get("evaluation") if isinstance(payload.get("evaluation"), dict) else {}
    )
    return {
        "active": bool(payload.get("active") is True),
        "model_type": str(model.get("type") or ""),
        "training_objective": str(training.get("objective") or ""),
        "split_policy": str(training.get("split_policy") or ""),
        "primary_metrics": list(evaluation.get("primary_metrics") or []),
    }


def _load_profile(profile_path: Path) -> dict[str, Any]:
    if not profile_path.exists():
        return {
            "path": str(profile_path),
            "is_active": False,
            "selected_feature_count": 0,
            "selected_feature_preview": [],
            "payload": None,
        }

    payload = _read_json(profile_path)
    selected = []
    if isinstance(payload, dict):
        selected = list(payload.get("selected_features") or [])
    elif isinstance(payload, list):
        selected = list(payload)
    selected_text = [str(x) for x in selected if str(x).strip()]
    return {
        "path": str(profile_path),
        "is_active": True,
        "selected_feature_count": len(selected_text),
        "selected_feature_preview": selected_text[:10],
        "payload": payload,
    }


def load_ann_info(
    *,
    selected_ticker: str,
    tickers: Sequence[str],
    store_summary: dict[str, Any],
    out_i_calc_dir: Path | None = None,
) -> dict[str, Any]:
    base_dir = (out_i_calc_dir or paths.OUT_I_CALC_DIR).resolve()
    ann_dir = base_dir / "ANN"
    tune_dir = ann_dir / "tuning"
    profile_path = base_dir / "ann" / "feature_profiles" / "pruned_inputs.json"
    selected_scope = _selected_tickers(selected_ticker, tickers)

    tune_run_id, tune_run_path = _latest_tune_run(tune_dir)
    matrix_path = (tune_run_path / "best_config_matrix.json") if tune_run_path else None
    matrix_payload = (
        _read_json(matrix_path)
        if matrix_path is not None and matrix_path.exists()
        else None
    )
    matrix_data = matrix_payload if isinstance(matrix_payload, dict) else {}

    ticker_payloads: dict[str, Any] = {}
    for ticker in selected_scope:
        setup_path = ann_dir / f"{ticker}.setup.json"
        setup_raw = _read_json(setup_path) if setup_path.exists() else None
        setup_data = setup_raw if isinstance(setup_raw, dict) else {}
        ticker_payloads[ticker] = {
            "setup_path": str(setup_path),
            "setup_exists": bool(setup_path.exists()),
            "setup": setup_data if setup_data else None,
            "setup_summary": _setup_summary(setup_data) if setup_data else {},
            "tune_matrix": matrix_data.get(ticker, {}),
        }

    return {
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "scope": {
            "selected_ticker": str(selected_ticker or ""),
            "selected_tickers": selected_scope,
            "count": len(selected_scope),
        },
        "paths": {
            "out_i_calc_dir": str(base_dir),
            "ann_dir": str(ann_dir),
            "tuning_dir": str(tune_dir),
            "feature_profile_path": str(profile_path),
        },
        "store_summary": dict(store_summary or {}),
        "profile": _load_profile(profile_path),
        "latest_tune": {
            "run_id": tune_run_id,
            "run_path": str(tune_run_path) if tune_run_path is not None else "",
            "matrix_path": str(matrix_path) if matrix_path is not None else "",
            "matrix_exists": bool(matrix_path is not None and matrix_path.exists()),
            "matrix_tickers": sorted(matrix_data.keys()),
        },
        "tickers": ticker_payloads,
    }


def build_ann_info_rows(info_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tickers = info_payload.get("tickers")
    if not isinstance(tickers, dict):
        return rows
    for ticker in sorted(tickers.keys()):
        payload = tickers.get(ticker)
        if not isinstance(payload, dict):
            continue
        setup_summary = (
            payload.get("setup_summary")
            if isinstance(payload.get("setup_summary"), dict)
            else {}
        )
        matrix = (
            payload.get("tune_matrix")
            if isinstance(payload.get("tune_matrix"), dict)
            else {}
        )
        mag = (
            matrix.get("magnitude") if isinstance(matrix.get("magnitude"), dict) else {}
        )
        sgn = matrix.get("sgn") if isinstance(matrix.get("sgn"), dict) else {}
        rows.append(
            {
                "Ticker": ticker,
                "Setup Exists": "Yes" if bool(payload.get("setup_exists")) else "No",
                "Model": str(setup_summary.get("model_type") or "N/A"),
                "Split Policy": str(setup_summary.get("split_policy") or "N/A"),
                "Magnitude Status": str(mag.get("status") or "N/A"),
                "SGN Status": str(sgn.get("status") or "N/A"),
            }
        )
    return rows


def build_ann_guides_markdown() -> str:
    return """
## ANN Operator Guide

### Run ANN Feature Ingest
- **What it runs:** `scripts/ann_feature_stores_ingest.py` via `run_ann_feature_stores_ingest`.
- **Source inputs:** `out/i_calc/TI/*.csv`, `out/i_calc/PP/*.csv`, `out/i_calc/svl/SVL_METRICS_*.csv`, `out/i_calc/tda/TDA_METRICS_*.csv`.
- **What it writes:** canonical ANN input SQLite store at `out/i_calc/stores/ann_input_features.sqlite` with family tables (`ti`, `pivot`, `hurst`, `tda_h1`).
- **How rows are handled:** records are upserted by `(as_of_date, ticker, feature_name)`; latest ingest updates prior values deterministically.
- **Operational result:** store summary metrics in ANN tab refresh after run (`Store Exists`, `Rows`, `Latest As-Of`, and per-family rows).

### Run ANN Marker Ingest (Legacy)
- **What it runs:** `scripts/ann_markers_ingest.py` via `run_ann_markers_ingest`.
- **Source inputs:** markdown-like marker tables in `data/raw/ann/*.txt`.
- **What it writes:** `out/i_calc/stores/ann_markers_store.sqlite` with normalized canonical marker names (for example `RD`, `85220`, `MICHO`, close markers).
- **Legacy note:** this marker ingest is maintained for marker-store workflows and diagnostics; ANN feature training pipeline uses the ANN input feature store from the Feature Ingest path.
- **Use case:** run when legacy marker source files changed and you need marker DB parity, not for normal ANN feature-store refresh.

### Parameter Guide
- **Window Length:** controls history window in ANN dataset construction (`--window-length`). Larger values provide more temporal context but reduce usable rows on short history ranges.
- **Lag Depth:** controls number of lagged feature copies (`--lag-depth`). Higher lag depth increases feature count and may improve temporal signal capture, but can raise overfit risk on small samples.
- **Tune Max Trials:** number of random hyperparameter trials in `ann_tune.py` (`--max-trials`). More trials can improve best config discovery but increase runtime.
- **Prune Keep Ratio:** percentage of features retained by importance pruning in `Prune Inputs` (`--importance-keep-ratio`). Example: `0.50` keeps roughly half the features selected by model-importance ranking.

### Button Guide
- **Prune Inputs:** runs ANN train in importance-selection mode, saves selected feature profile to `out/i_calc/ann/feature_profiles/pruned_inputs.json`, and updates active input profile.
- **Run ANN Train:** runs `scripts/ann_train.py` for selected ticker scope (ALL or single), applying current UI parameters and optional allowlist profile if prune profile exists.
- **Run ANN Tune:** runs `scripts/ann_tune.py` with trial count from `Tune Max Trials`; produces tuning artifacts under `out/i_calc/ANN/tuning/tune_*` including matrix outputs.
- **Info:** displays known ANN setup and tuning state from local artifacts for selected scope. With sidebar `ALL`, info covers all tickers; with single ticker selected, info is filtered to that ticker.
""".strip()


__all__ = [
    "build_ann_guides_markdown",
    "build_ann_info_rows",
    "load_ann_info",
]
