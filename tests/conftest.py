# ------------------------
# tests/conftest.py
# ------------------------# tests/conftest.py
"""
Pytest configuration for FIN test plan.

Goals
- Avoid Windows temp ACL failures by forcing a repo-local basetemp.
- Provide a CPI acceptance layer that is skipped by default.
- Enable CPI tests explicitly via: pytest --run-cpi

Design
- Phase-1 guardrails: always executed.
- CPI acceptance: marked with @pytest.mark.cpi and skipped unless --run-cpi is set.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-cpi",
        action="store_true",
        default=False,
        help="Enable CPI acceptance tests (marked with @pytest.mark.cpi).",
    )


def pytest_configure(config: pytest.Config) -> None:
    # Register marker for clarity in -m listings and IDEs.
    config.addinivalue_line(
        "markers",
        "cpi: CPI acceptance tests (skipped unless --run-cpi is provided).",
    )

    # Force a writable basetemp under the repository root unless explicitly provided.
    if getattr(config.option, "basetemp", None):
        return

    repo_root = Path(__file__).resolve().parents[1]
    base = repo_root / ".pytest_tmp"
    base.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(base)


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    run_cpi = bool(config.getoption("--run-cpi"))
    if run_cpi:
        return

    skip_cpi = pytest.mark.skip(reason="CPI acceptance tests disabled (enable with --run-cpi).")
    for item in items:
        if "cpi" in item.keywords:
            item.add_marker(skip_cpi)
