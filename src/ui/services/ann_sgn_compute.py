from __future__ import annotations

from typing import Any

from src.ui.services.ann_sgn_map import (
    evaluate_sgn_suggestion_from_context,
    prepare_sgn_probability_context,
)


def continuation_sgn(*, trend_sign: str, realized_or_predicted_sign: str) -> str:
    trend = str(trend_sign or "").strip()
    candidate = str(realized_or_predicted_sign or "").strip()
    if trend not in {"+", "-"} or candidate not in {"+", "-"}:
        return ""
    return "+" if trend == candidate else "-"


def predict_ann_computed_sgn_overrides(
    *,
    selected_date: str,
    tickers: list[str],
    compare_rows: list[dict[str, Any]],
    map_context_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    compare_map = {
        str(row.get("Ticker") or "").strip().upper(): str(
            row.get("Computed SGN") or ""
        ).strip()
        for row in compare_rows
    }
    out: dict[str, str] = {}
    details: list[dict[str, Any]] = []
    cache = map_context_cache if map_context_cache is not None else {}

    for ticker in [str(x).strip().upper() for x in tickers if str(x).strip()]:
        trend_sign = str(compare_map.get(ticker) or "").strip()
        if trend_sign not in {"+", "-"}:
            out[ticker] = ""
            details.append(
                {
                    "Ticker": ticker,
                    "Trend Sign": trend_sign or "N/A",
                    "Predicted Real Sign": "N/A",
                    "Computed SGN": "N/A",
                    "Confidence": "N/A",
                    "Reason": "trend_sign_unavailable",
                }
            )
            continue

        context = cache.get(ticker)
        if not isinstance(context, dict):
            context = prepare_sgn_probability_context(ticker=ticker)
            cache[ticker] = context

        payload = evaluate_sgn_suggestion_from_context(
            context=context,
            selected_date=str(selected_date or "").strip(),
            computed_sgn=trend_sign,
        )
        suggestion_raw = payload.get("suggested_real_sgn")
        suggestion = suggestion_raw if isinstance(suggestion_raw, dict) else {}
        value = str(suggestion.get("value") or "").strip()
        predicted_real_sign = "+" if value == "+1" else "-" if value == "-1" else ""
        reason_text = str(suggestion.get("reason") or "").strip()
        if predicted_real_sign in {"+", "-"}:
            computed_sgn = continuation_sgn(
                trend_sign=trend_sign,
                realized_or_predicted_sign=predicted_real_sign,
            )
            detail_reason = reason_text
        else:
            computed_sgn = trend_sign
            base_reason = reason_text or "selected_point_unavailable"
            detail_reason = f"{base_reason}|fallback_trend_sign"

        out[ticker] = computed_sgn
        details.append(
            {
                "Ticker": ticker,
                "Trend Sign": trend_sign,
                "Predicted Real Sign": predicted_real_sign or "N/A",
                "Computed SGN": computed_sgn or "N/A",
                "Confidence": f"{float(suggestion.get('confidence') or 0.0):.3f}",
                "Reason": detail_reason,
            }
        )

    return {
        "computed_sgn_overrides": out,
        "details": details,
    }


__all__ = ["continuation_sgn", "predict_ann_computed_sgn_overrides"]
