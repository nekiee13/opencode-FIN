from __future__ import annotations

from typing import Any, Iterable


def build_field_diffs(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    tracked_fields: Iterable[str],
) -> list[tuple[str, str | None, str | None]]:
    out: list[tuple[str, str | None, str | None]] = []
    before_data = before or {}
    for field_name in tracked_fields:
        old_val = before_data.get(field_name)
        new_val = after.get(field_name)
        if old_val != new_val:
            out.append(
                (
                    field_name,
                    None if old_val is None else str(old_val),
                    None if new_val is None else str(new_val),
                )
            )
    return out
