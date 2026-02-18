# ------------------------
# conftest.py (repo root)
# ------------------------
from __future__ import annotations

import sys
import warnings
from pathlib import Path


def pytest_configure() -> None:
    """
    Phase-1 import stability guard:
    ensure repository root is on sys.path so top-level packages like `compat` resolve.

    Also installs warning filters early to suppress known third-party noise:
    - pkg_resources deprecation warning (often attributed to importing module via stacklevel, e.g. fs)
    - scikit-learn coordinate descent ConvergenceWarning in smoke tests
    """
    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # P0: setuptools/pkg_resources deprecation warning.
    # The warning is raised inside pkg_resources but attributed to the importer (e.g. fs) via stacklevel,
    # so do NOT restrict by module here; match the message instead.
    warnings.filterwarnings(
        "ignore",
        message=r"pkg_resources is deprecated as an API\..*",
        category=UserWarning,
    )

    # P1: scikit-learn coordinate descent convergence noise (Lasso/ElasticNet).
    try:
        from sklearn.exceptions import ConvergenceWarning  # type: ignore
    except Exception:
        ConvergenceWarning = None  # type: ignore[assignment]

    if ConvergenceWarning is not None:
        warnings.filterwarnings(
            "ignore",
            message=r".*Objective did not converge.*",
            category=ConvergenceWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r".*Duality gap.*",
            category=ConvergenceWarning,
        )
