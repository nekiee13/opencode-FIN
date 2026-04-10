from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from src.config import paths
from src.ui.services.ann_info import load_ann_info
from src.ui.services.vg_loader import build_ann_real_vs_computed_rows


def _coerce_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _mode_status_note(mode_rows: list[dict[str, Any]]) -> str:
    failed: list[str] = []
    for row in mode_rows:
        mode = str(row.get("Mode") or "")
        status = str(row.get("Status") or "").strip().lower()
        if status in {"fails_baseline", "insufficient_data"}:
            failed.append(f"{mode}={status}")
    if not failed:
        return "All available modes are healthy or unavailable."
    return "; ".join(failed)


def _mode_detail_rows(
    *,
    tune_matrix: dict[str, Any],
    setup_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode in ("magnitude", "sgn"):
        payload = _coerce_payload(tune_matrix.get(mode))
        rows.append(
            {
                "Mode": mode,
                "Status": payload.get("status", "N/A"),
                "Features Before": payload.get("features_before", "N/A"),
                "Features After": payload.get("features_after", "N/A"),
                "R2": payload.get("r2", "N/A"),
                "MAE": payload.get("mae", "N/A"),
                "RMSE": payload.get("rmse", "N/A"),
                "Directional Accuracy": payload.get("directional_accuracy", "N/A"),
                "Epochs": payload.get("epochs", "N/A"),
                "Learning Rate": payload.get("learning_rate", "N/A"),
                "Batch Size": payload.get("batch_size", "N/A"),
                "Depth": payload.get("depth", "N/A"),
                "Width": payload.get("width", "N/A"),
                "Dropout": payload.get("dropout", "N/A"),
                "Weight Decay": payload.get("weight_decay", "N/A"),
                "Window Length": payload.get("window_length", "N/A"),
                "Lag Depth": payload.get("lag_depth", "N/A"),
                "Model": setup_summary.get("model_type", "N/A"),
                "Split Policy": setup_summary.get("split_policy", "N/A"),
                "Training Objective": setup_summary.get("training_objective", "N/A"),
            }
        )
    return rows


def _empty_compare_row(ticker: str) -> dict[str, str]:
    return {
        "Ticker": ticker,
        "Real SGN": "",
        "Computed SGN": "",
        "Real Magnitude": "",
        "Computed Magnitude": "",
    }


def load_ann_report_sections(
    *,
    selected_date: str,
    tickers: Sequence[str],
    out_i_calc_dir: Path | None = None,
    rounds_dir: Path | None = None,
    raw_tickers_dir: Path | None = None,
) -> dict[str, Any]:
    canonical = [str(x).strip().upper() for x in tickers if str(x).strip()]
    base_dir = (out_i_calc_dir or paths.OUT_I_CALC_DIR).resolve()

    compare_rows = build_ann_real_vs_computed_rows(
        selected_date=selected_date,
        tickers=canonical,
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_tickers_dir,
    )
    compare_map = {
        str(row.get("Ticker") or "").strip().upper(): row for row in compare_rows
    }

    info_payload = load_ann_info(
        selected_ticker="ALL",
        tickers=canonical,
        store_summary={},
        out_i_calc_dir=base_dir,
    )
    latest_tune = _coerce_payload(info_payload.get("latest_tune"))
    ticker_payloads = _coerce_payload(info_payload.get("tickers"))

    sections: dict[str, dict[str, Any]] = {}
    for ticker in canonical:
        item = _coerce_payload(ticker_payloads.get(ticker))
        tune_matrix = _coerce_payload(item.get("tune_matrix"))
        setup_summary = _coerce_payload(item.get("setup_summary"))
        setup_rows = _mode_detail_rows(
            tune_matrix=tune_matrix, setup_summary=setup_summary
        )
        sections[ticker] = {
            "compare_row": compare_map.get(ticker, _empty_compare_row(ticker)),
            "best_setup_rows": setup_rows,
            "status_note": _mode_status_note(setup_rows),
            "setup_path": str(item.get("setup_path") or ""),
        }

    return {
        "selected_date": str(selected_date or ""),
        "latest_tune_run_id": str(latest_tune.get("run_id") or ""),
        "latest_tune_run_path": str(latest_tune.get("run_path") or ""),
        "sections": sections,
    }


__all__ = ["load_ann_report_sections"]
