from __future__ import annotations

from typing import Any

from src.review.service import load_available_review_dates


def load_sidebar_date_options() -> list[str]:
    items = load_available_review_dates()
    out: list[str] = []
    for item in items:
        value = str(item.get("review_date", "") or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def load_sidebar_date_records() -> list[dict[str, Any]]:
    return list(load_available_review_dates())
