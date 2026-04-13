from __future__ import annotations

from typing import Any, Sequence

from src.ui.services.ann_sgn_compute import predict_ann_computed_sgn_overrides
from src.ui.services.date_sources import load_sidebar_date_options
from src.ui.services.vg_loader import (
    build_ann_real_vs_computed_rows,
    build_ann_t0_p_sgn_rows,
)

TICKER_ORDER: tuple[str, ...] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")


def _sgn_value(raw: Any) -> str:
    text = str(raw or "").strip()
    if text in {"+", "-"}:
        return text
    if text in {"+1", "1"}:
        return "+"
    if text in {"-1"}:
        return "-"
    return ""


def _to_float(raw: Any) -> float | None:
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value != value:
        return None
    return float(value)


def compute_ann_overall_stats(
    *,
    dates: Sequence[str] | None = None,
    tickers: Sequence[str] | None = None,
) -> dict[str, Any]:
    use_dates = [
        str(x).strip() for x in (dates or load_sidebar_date_options()) if str(x).strip()
    ]
    use_tickers = [
        str(x).strip().upper() for x in (tickers or TICKER_ORDER) if str(x).strip()
    ]

    total = 0
    success = 0
    gap_sum: dict[str, float] = {t: 0.0 for t in use_tickers}
    gap_count: dict[str, int] = {t: 0 for t in use_tickers}
    delta_gt_magnitude_count: dict[str, int] = {t: 0 for t in use_tickers}
    failed_sgn_rows: list[dict[str, Any]] = []
    magnitude_gt_delta_rows: list[dict[str, Any]] = []
    map_context_cache: dict[str, dict[str, Any]] = {}

    for selected_date in use_dates:
        compare_rows = build_ann_real_vs_computed_rows(
            selected_date=selected_date,
            tickers=list(use_tickers),
        )
        overrides_payload = predict_ann_computed_sgn_overrides(
            selected_date=selected_date,
            tickers=list(use_tickers),
            compare_rows=list(compare_rows),
            map_context_cache=map_context_cache,
        )
        overrides_raw = overrides_payload.get("computed_sgn_overrides")
        overrides = dict(overrides_raw) if isinstance(overrides_raw, dict) else {}

        signal_rows = build_ann_t0_p_sgn_rows(
            selected_date=selected_date,
            tickers=list(use_tickers),
            computed_sgn_overrides=overrides,
        )

        for row in signal_rows:
            ticker = str(row.get("Ticker") or "").strip().upper()
            if ticker not in gap_sum:
                continue

            realized_sgn = _sgn_value(row.get("Realized SGN"))
            computed_sgn = _sgn_value(row.get("Computed SGN"))
            if realized_sgn and computed_sgn:
                total += 1
                if realized_sgn == computed_sgn:
                    success += 1
                else:
                    failed_sgn_rows.append(
                        {
                            "Date": str(selected_date),
                            "Ticker": ticker,
                            "Realized SGN": realized_sgn,
                            "Computed SGN": computed_sgn,
                            "Delta": str(row.get("Delta") or "N/A"),
                            "Magnitude": str(row.get("Magnitude") or "N/A"),
                        }
                    )

            delta = _to_float(row.get("Delta"))
            magnitude = _to_float(row.get("Magnitude"))
            if delta is None or magnitude is None:
                continue

            abs_delta = abs(float(delta))
            abs_magnitude = abs(float(magnitude))
            gap_sum[ticker] += abs(abs_delta - abs_magnitude)
            gap_count[ticker] += 1
            if abs_delta > abs_magnitude:
                delta_gt_magnitude_count[ticker] += 1

            if abs(magnitude) > abs(delta):
                ratio_pct_text = (
                    f"{(abs_magnitude / abs_delta) * 100.0:.2f}"
                    if abs_delta > 0.0
                    else "INF"
                )
                magnitude_gt_delta_rows.append(
                    {
                        "Date": str(selected_date),
                        "Ticker": ticker,
                        "Delta": f"{float(delta):.4f}",
                        "Magnitude": f"{float(magnitude):.4f}",
                        "Ratio (% of Delta)": ratio_pct_text,
                    }
                )

    rows_out: list[dict[str, Any]] = []
    for ticker in use_tickers:
        cnt = int(gap_count.get(ticker) or 0)
        avg_gap = float(gap_sum.get(ticker) or 0.0) / float(cnt) if cnt > 0 else None
        delta_gt_pct = (
            (float(delta_gt_magnitude_count.get(ticker) or 0) / float(cnt)) * 100.0
            if cnt > 0
            else None
        )
        display = (
            f"{avg_gap:.2f} ({delta_gt_pct:.0f}% D>M)"
            if avg_gap is not None and delta_gt_pct is not None
            else "N/A"
        )
        rows_out.append(
            {
                "Ticker": ticker,
                "Gap (D>M%)": display,
                "Rows Used": int(cnt),
            }
        )

    success_rate = float(success) / float(total) if total > 0 else 0.0
    return {
        "dates_count": int(len(use_dates)),
        "success_count": int(success),
        "total_count": int(total),
        "success_rate": float(success_rate),
        "success_label": f"{int(success)}/{int(total)} ({success_rate:.2%})"
        if total > 0
        else "0/0 (N/A)",
        "magnitude_gap_rows": rows_out,
        "magnitude_ratio_rows": rows_out,
        "failed_sgn_count": int(len(failed_sgn_rows)),
        "failed_sgn_rows": failed_sgn_rows,
        "magnitude_gt_delta_count": int(len(magnitude_gt_delta_rows)),
        "magnitude_gt_delta_rows": magnitude_gt_delta_rows,
    }


__all__ = ["compute_ann_overall_stats"]
