from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from src.config import paths
from src.ui.services.ann_info import load_ann_info
from src.ui.services.vg_loader import build_ann_real_vs_computed_rows


def _coerce_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _selected_tickers(selected_ticker: str, tickers: Sequence[str]) -> list[str]:
    value = str(selected_ticker or "").strip().upper()
    canonical = [str(x).strip().upper() for x in tickers if str(x).strip()]
    if value in {"", "ALL", "ALL_TICKERS"}:
        return canonical
    return [value]


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


def build_export_filename(*, selected_date: str, selected_ticker: str) -> str:
    date_part = str(selected_date or "").strip() or "NA"
    ticker_part = str(selected_ticker or "").strip().upper() or "ALL"
    return f"Export_report_{date_part}_{ticker_part}.md"


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_No rows available._"
    columns = [str(x) for x in rows[0].keys()]
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join([header, divider, *body])


def build_ann_report_markdown(
    *,
    report_payload: dict[str, Any],
    selected_date: str,
    selected_ticker: str,
) -> str:
    lines: list[str] = []
    lines.append("# ANN Report")
    lines.append("")
    lines.append(
        f"- Generated At (UTC): {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}"
    )
    lines.append(f"- Selected Date: {str(selected_date or '').strip()}")
    lines.append(
        f"- Selected Ticker Option: {str(selected_ticker or '').strip().upper() or 'ALL'}"
    )
    lines.append(
        f"- Latest Tune Run: {str(report_payload.get('latest_tune_run_id') or 'N/A')}"
    )
    lines.append("")

    sections_raw = report_payload.get("sections")
    sections = sections_raw if isinstance(sections_raw, dict) else {}
    for ticker, payload_raw in sections.items():
        payload = payload_raw if isinstance(payload_raw, dict) else {}
        lines.append(f"## {ticker}")
        lines.append("")
        lines.append("### Real vs Computed (SGN / Magnitude)")
        compare = payload.get("compare_row")
        compare_row = compare if isinstance(compare, dict) else {"Ticker": ticker}
        lines.append(_markdown_table([compare_row]))
        lines.append("")
        lines.append("### Best ANN Setup Details")
        setup_rows_raw = payload.get("best_setup_rows")
        setup_rows = setup_rows_raw if isinstance(setup_rows_raw, list) else []
        lines.append(_markdown_table(setup_rows))
        status_note = str(payload.get("status_note") or "").strip()
        if status_note:
            lines.append("")
            lines.append(f"- Status Note: {status_note}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def export_ann_report_markdown(
    *,
    selected_date: str,
    selected_ticker: str,
    tickers: Sequence[str],
    out_i_calc_dir: Path | None = None,
    rounds_dir: Path | None = None,
    raw_tickers_dir: Path | None = None,
) -> dict[str, Any]:
    selected_scope = _selected_tickers(selected_ticker, tickers)
    base_dir = (out_i_calc_dir or paths.OUT_I_CALC_DIR).resolve()
    report_payload = load_ann_report_sections(
        selected_date=selected_date,
        tickers=selected_scope,
        out_i_calc_dir=base_dir,
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_tickers_dir,
    )
    markdown = build_ann_report_markdown(
        report_payload=report_payload,
        selected_date=selected_date,
        selected_ticker=selected_ticker,
    )
    output_dir = base_dir / "ANN" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / build_export_filename(
        selected_date=selected_date,
        selected_ticker=selected_ticker,
    )
    output_path.write_text(markdown, encoding="utf-8")
    return {
        "output_path": str(output_path),
        "scope_tickers": selected_scope,
        "latest_tune_run_id": str(report_payload.get("latest_tune_run_id") or ""),
        "bytes_written": len(markdown.encode("utf-8")),
    }


__all__ = [
    "build_ann_report_markdown",
    "build_export_filename",
    "export_ann_report_markdown",
    "load_ann_report_sections",
]
