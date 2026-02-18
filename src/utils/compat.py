# ------------------------
# src/utils/compat.py
# ------------------------
"""
FIN Optional Dependency Compatibility Layer.

Canonical location: src.utils.compat

Purpose
-------
Centralized, import-safe capability detection for optional dependencies used across
FIN.

This module must:
  - never hard-fail when an optional package is missing
  - expose clear boolean flags (HAS_*) for feature gating
  - provide safe imported symbols (or None) for downstream modules
  - be side-effect safe (no file I/O; logging only)

SVL-v1.0 base requirements (soft-required)
-----------------------------------------
  - numpy
  - pandas

TDA Phase 2A base requirements (soft-required)
---------------------------------------------
  - numpy
  - pandas
  - ripser

Notes
-----
- This module intentionally performs *capability detection* at import time.
  That is acceptable because it has no filesystem mutation and will not crash
  when packages are missing.
- Some heavy libraries (e.g., tensorflow) are imported only if present; for true
  "lazy import" behavior inside model execution, keep imports local in model
  functions as a separate refactor step.
"""

from __future__ import annotations

import logging
from importlib import util
from typing import TYPE_CHECKING

log = logging.getLogger(__name__)


def _spec_exists(pkg_name: str) -> bool:
    """Return True if importlib can find a package spec."""
    try:
        return util.find_spec(pkg_name) is not None
    except (ImportError, ValueError):
        # Defensive: some environments raise ValueError for malformed spec state
        return False


# --------------------------------------------------------------------
# SVL-v1.0 (Structural Indicators) - Soft-required base stack
# --------------------------------------------------------------------

HAS_NUMPY = _spec_exists("numpy")
if HAS_NUMPY:
    import numpy as np  # noqa: F401, E402

    log.info("Dependency 'numpy' found. SVL numeric operations available.")
else:
    if TYPE_CHECKING:
        import numpy as np  # type: ignore  # noqa: F401, E402
    else:
        np = None  # type: ignore
    log.warning("Dependency 'numpy' not found. SVL features will be disabled.")


HAS_PANDAS = _spec_exists("pandas")
if HAS_PANDAS:
    import pandas as pd  # noqa: F401, E402

    log.info("Dependency 'pandas' found. SVL time series operations available.")
else:
    if TYPE_CHECKING:
        import pandas as pd  # type: ignore  # noqa: F401, E402
    else:
        pd = None  # type: ignore
    log.warning("Dependency 'pandas' not found. SVL features will be disabled.")


HAS_SVL = HAS_NUMPY and HAS_PANDAS
if HAS_SVL:
    log.info("SVL base stack available (numpy+pandas). SVL features enabled.")
else:
    log.warning("SVL base stack missing (numpy and/or pandas). SVL features disabled.")

# Hurst support is part of SVL-v1.0 base stack.
HAS_SVL_HURST = HAS_SVL


# Optional helper dependency for data acquisition scripts (not required by SVL core)
HAS_YFINANCE = _spec_exists("yfinance")
if HAS_YFINANCE:
    import yfinance as yf  # noqa: F401, E402

    log.info(
        "Optional dependency 'yfinance' found. yfinance-based data fetch will be available."
    )
else:
    if TYPE_CHECKING:
        import yfinance as yf  # type: ignore  # noqa: F401, E402
    else:
        yf = None  # type: ignore
    log.info(
        "Optional dependency 'yfinance' not found. yfinance-based data fetch will be unavailable."
    )


# --------------------------------------------------------------------
# TDA Phase 2A (Persistent Homology via ripser)
# --------------------------------------------------------------------

HAS_RIPSER = _spec_exists("ripser")
if HAS_RIPSER:
    # ripser.py exports a 'ripser' function; we expose both the function and module.
    import ripser as ripser_module  # noqa: F401, E402

    try:
        from ripser import ripser  # noqa: F401, E402
    except Exception:
        ripser = None  # type: ignore
        ripser_module = None  # type: ignore
        HAS_RIPSER = False
        log.warning(
            "Optional dependency 'ripser' found but could not import ripser.ripser(). TDA disabled."
        )
    else:
        log.info("Optional dependency 'ripser' found. TDA Phase 2A will be available.")
else:
    if TYPE_CHECKING:
        import ripser as ripser_module  # type: ignore  # noqa: F401, E402
        from ripser import ripser  # type: ignore  # noqa: F401, E402
    else:
        ripser_module = None  # type: ignore
        ripser = None  # type: ignore
    log.info("Optional dependency 'ripser' not found. TDA Phase 2A will be disabled.")


HAS_TDA = HAS_NUMPY and HAS_PANDAS and HAS_RIPSER
if HAS_TDA:
    log.info("TDA base stack available (numpy+pandas+ripser). TDA Phase 2A enabled.")
else:
    log.info(
        "TDA base stack missing (numpy and/or pandas and/or ripser). TDA Phase 2A disabled."
    )


# --------------------------------------------------------------------
# Ruptures (for Regime Detection overlays)
# --------------------------------------------------------------------

HAS_RUPTURES = _spec_exists("ruptures")
if HAS_RUPTURES:
    import ruptures as rpt  # noqa: F401, E402

    log.info(
        "Optional dependency 'ruptures' found. Regime detection overlays will be available."
    )
else:
    if TYPE_CHECKING:
        import ruptures as rpt  # type: ignore  # noqa: F401, E402
    else:
        rpt = None  # type: ignore
    log.warning(
        "Optional dependency 'ruptures' not found. Regime detection overlays will be disabled."
    )


# --------------------------------------------------------------------
# TensorFlow (for LSTM Model)
# --------------------------------------------------------------------

HAS_TENSORFLOW = _spec_exists("tensorflow")
if HAS_TENSORFLOW:
    import tensorflow as tf  # noqa: F401, E402

    log.info("Dependency 'tensorflow' found. LSTM model will be available.")
else:
    if TYPE_CHECKING:
        import tensorflow as tf  # type: ignore  # noqa: F401, E402
    else:
        tf = None  # type: ignore
    log.warning("Dependency 'tensorflow' not found. LSTM model will be disabled.")


# --------------------------------------------------------------------
# ARCH (for GARCH Models)
# --------------------------------------------------------------------

HAS_ARCH = _spec_exists("arch")
if HAS_ARCH:
    try:
        from arch import arch_model  # noqa: F401, E402
    except Exception:
        # Module exists but import failed; treat as unavailable.
        HAS_ARCH = False
        arch_model = None  # type: ignore
        log.warning(
            "Dependency 'arch' found but could not import arch.arch_model. GARCH disabled."
        )
    else:
        log.info("Dependency 'arch' found. GARCH modeling will be available.")
else:
    if TYPE_CHECKING:
        from arch import arch_model  # type: ignore  # noqa: F401, E402
    else:
        arch_model = None  # type: ignore
    log.warning("Dependency 'arch' not found. GARCH modeling will be disabled.")


# --------------------------------------------------------------------
# Statsmodels (for VAR model)
# --------------------------------------------------------------------

HAS_STATSMODELS = _spec_exists("statsmodels")
if HAS_STATSMODELS:
    try:
        import statsmodels.api as sm  # noqa: F401, E402
        from statsmodels.tsa.api import VAR  # noqa: F401, E402
    except Exception:
        HAS_STATSMODELS = False
        sm = None  # type: ignore
        VAR = None  # type: ignore
        log.warning(
            "Dependency 'statsmodels' found but could not import required symbols. VAR disabled."
        )
    else:
        log.info("Dependency 'statsmodels' found. VAR modeling will be available.")
else:
    if TYPE_CHECKING:
        import statsmodels.api as sm  # type: ignore  # noqa: F401, E402
        from statsmodels.tsa.api import VAR  # type: ignore  # noqa: F401, E402
    else:
        sm = None  # type: ignore
        VAR = None  # type: ignore
    log.warning("Dependency 'statsmodels' not found. VAR modeling will be disabled.")


# --------------------------------------------------------------------
# Convenience: expose a compact capability summary if needed by callers
# --------------------------------------------------------------------

CAPABILITIES = {
    # SVL
    "HAS_NUMPY": HAS_NUMPY,
    "HAS_PANDAS": HAS_PANDAS,
    "HAS_SVL": HAS_SVL,
    "HAS_SVL_HURST": HAS_SVL_HURST,
    "HAS_YFINANCE": HAS_YFINANCE,
    # TDA (Phase 2A)
    "HAS_RIPSER": HAS_RIPSER,
    "HAS_TDA": HAS_TDA,
    # Existing project flags
    "HAS_RUPTURES": HAS_RUPTURES,
    "HAS_TENSORFLOW": HAS_TENSORFLOW,
    "HAS_ARCH": HAS_ARCH,
    "HAS_STATSMODELS": HAS_STATSMODELS,
}


# --------------------------------------------------------------------
# Optional: quick diagnostic when running module directly
# --------------------------------------------------------------------

if __name__ == "__main__":
    import pprint  # noqa: E402

    pprint.pprint(CAPABILITIES, sort_dicts=True)
