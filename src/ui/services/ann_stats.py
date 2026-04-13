from __future__ import annotations

from typing import Any, Sequence

from src.ui.services.date_sources import load_sidebar_date_options
from src.ui.services.vg_loader import build_ann_real_vs_computed_rows

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
    ratio_sum: dict[str, float] = {t: 0.0 for t in use_tickers}
    ratio_count: dict[str, int] = {t: 0 for t in use_tickers}

    for selected_date in use_dates:
        rows = build_ann_real_vs_computed_rows(
            selected_date=selected_date,
            tickers=list(use_tickers),
        )
        for row in rows:
            ticker = str(row.get("Ticker") or "").strip().upper()
            if ticker not in ratio_sum:
                continue

            real_sgn = _sgn_value(row.get("Real SGN"))
            computed_sgn = _sgn_value(row.get("Computed SGN"))
            if real_sgn and computed_sgn:
                total += 1
                if real_sgn == computed_sgn:
                    success += 1

            real_mag = _to_float(row.get("Real Magnitude"))
            comp_mag = _to_float(row.get("Computed Magnitude"))
            if real_mag is None or comp_mag is None or abs(real_mag) <= 0.0:
                continue
            ratio_sum[ticker] += abs(float(comp_mag)) / abs(float(real_mag))
            ratio_count[ticker] += 1

    rows_out: list[dict[str, Any]] = []
    for ticker in use_tickers:
        cnt = int(ratio_count.get(ticker) or 0)
        ratio_pct = (
            float(ratio_sum.get(ticker) or 0.0) / float(cnt) * 100.0
            if cnt > 0
            else None
        )
        rows_out.append(
            {
                "Ticker": ticker,
                "Magnitude (% of Delta)": f"{ratio_pct:.2f}"
                if ratio_pct is not None
                else "N/A",
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
        "magnitude_ratio_rows": rows_out,
    }


__all__ = ["compute_ann_overall_stats"]
