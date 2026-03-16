from __future__ import annotations

import pytest

from src.followup_ml.scope_audit import (
    EXCEPTION_LABEL,
    SCOPE_LABEL,
    ScopeAuditError,
    compute_scope_audit,
    default_scope_audit_report_path,
    render_scope_audit_markdown,
)


def test_compute_scope_audit_counts() -> None:
    records = [
        {
            "number": 10,
            "title": "scope change A",
            "url": "https://example/pr/10",
            "mergedAt": "2026-03-10T10:00:00Z",
            "labels": [{"name": SCOPE_LABEL}],
        },
        {
            "number": 11,
            "title": "approved exception",
            "url": "https://example/pr/11",
            "mergedAt": "2026-03-11T10:00:00Z",
            "labels": [{"name": EXCEPTION_LABEL}],
        },
        {
            "number": 12,
            "title": "missing labels",
            "url": "https://example/pr/12",
            "mergedAt": "2026-03-12T10:00:00Z",
            "labels": [],
        },
    ]

    result = compute_scope_audit(
        repo="nekiee13/opencode-FIN", since="2026-03-01", records=records
    )

    assert result.total_merged_prs == 3
    assert result.exception_merges_count == 1
    assert result.missing_scope_label_merges_count == 1
    assert result.violations_count == 1
    assert result.exception_prs[0].number == 11
    assert result.missing_scope_label_prs[0].number == 12


def test_render_scope_audit_markdown_pass() -> None:
    records = [
        {
            "number": 20,
            "title": "scope-labeled change",
            "url": "https://example/pr/20",
            "mergedAt": "2026-03-15T00:00:00Z",
            "labels": [{"name": SCOPE_LABEL}],
        }
    ]

    result = compute_scope_audit(
        repo="nekiee13/opencode-FIN", since="2026-03-01", records=records
    )
    md = render_scope_audit_markdown(result)

    assert "Result: `PASS`" in md
    assert "Exception merges (`m5-expansion-exception`): `0`" in md
    assert "Missing-scope-label merges" in md
    assert "| - | - | none |" in md


def test_default_scope_audit_report_path_invalid_date() -> None:
    with pytest.raises(ScopeAuditError, match="Invalid --since date"):
        default_scope_audit_report_path(since="2026/03/01")
