# ------------------------
# src\exo\exo_config.py
# ------------------------
"""
FIN exogenous regressor configuration loader.

Location
--------
src/exo/exo_config.py

Purpose
-------
Load and serve exogenous-regressor configuration and scenario paths from a CSV.

CSV schema (ticker-first)
-------------------------
    Ticker,Model,Regressor,Enabled,ScenarioMode,Day_1,Day_2,...,Day_FH

Semantics
---------
- Enabled: TRUE/1/YES (case-insensitive) enables the regressor for that (model,ticker).
- ScenarioMode: NONE | DELTA | ABS
  - NONE  : ignore scenario values even if present
  - DELTA : treat Day_k as additive delta to the baseline regressor
  - ABS   : treat Day_k as absolute regressor values for the forecast horizon

Design invariants
-----------------
- No filesystem mutation on import.
- Robust parsing: invalid rows are skipped with warnings; function returns best-effort config.
- Forecast-horizon aware: Day_* columns are truncated to forecast_horizon.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union, cast

import pandas as pd

log = logging.getLogger(__name__)

PathLike = Union[str, Path]


# =============================================================================
# Types
# =============================================================================

ScenarioMode = str  # "NONE" | "DELTA" | "ABS"

# Nested config:
# config[model][ticker][regressor] = {"enabled": bool, "scenario_mode": str, "values": List[float|None]}
ExoConfigType = Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]


@dataclass(frozen=True)
class ExoSpec:
    enabled: bool
    scenario_mode: ScenarioMode
    values: List[Optional[float]]


# =============================================================================
# Helpers
# =============================================================================

def _sort_day_columns(columns: Sequence[str]) -> List[str]:
    """Sort columns like ['Day_2', 'Day_10', 'Day_1'] by numeric suffix."""
    def extract_num(c: str) -> int:
        try:
            return int(str(c).split("_", 1)[1])
        except Exception:
            return 999_999

    return sorted([str(c) for c in columns], key=extract_num)


def _parse_bool(v: Any) -> bool:
    s = str(v).strip().upper()
    return s in ("TRUE", "1", "YES", "Y", "T")


def _parse_scenario_mode(v: Any) -> Optional[str]:
    s = str(v).strip().upper()
    if s in ("NONE", "DELTA", "ABS"):
        return s
    return None


def _to_float_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
            return None if pd.isna(f) else f
        except Exception:
            return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None


def _strip_trailing_nones(values: List[Optional[float]]) -> List[Optional[float]]:
    out = list(values)
    while out and out[-1] is None:
        out.pop()
    return out


def _resolve_csv_path(csv_path: PathLike) -> Path:
    p = Path(csv_path).expanduser()
    try:
        return p.resolve()
    except Exception:
        # On some Windows edge cases resolve can fail if drive is unavailable; keep best effort.
        return p


# =============================================================================
# Public API
# =============================================================================

def load_exo_config(csv_path: PathLike, forecast_horizon: int) -> ExoConfigType:
    """
    Load exogenous regressor configuration from CSV.

    Returns
    -------
    ExoConfigType
        Nested dict:
            config[model][ticker][regressor] = {
                "enabled": bool,
                "scenario_mode": "NONE" | "DELTA" | "ABS",
                "values": List[float | None],   # truncated to forecast_horizon (and trailing Nones removed)
            }
        Returns {} if file is missing/unreadable or schema invalid.
    """
    cfg: ExoConfigType = {}

    path = _resolve_csv_path(csv_path)
    if not path.exists():
        log.warning("Exogenous config file not found: %s. No exogenous configuration will be applied.", path)
        return cfg

    try:
        df = pd.read_csv(path)
    except Exception as e:
        log.error("Failed to read exogenous config CSV: %s. Error: %s", path, e, exc_info=True)
        return cfg

    if df is None or df.empty:
        log.warning("Exogenous config CSV is empty: %s. No exogenous configuration will be applied.", path)
        return cfg

    required_cols = ["Ticker", "Model", "Regressor", "Enabled", "ScenarioMode"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        log.error(
            "Exogenous config CSV missing required columns %s (file: %s). No exogenous configuration will be used.",
            missing,
            path,
        )
        return cfg

    day_cols = [c for c in df.columns if str(c).startswith("Day_")]
    day_cols_sorted = _sort_day_columns(day_cols)
    if int(forecast_horizon) > 0:
        day_cols_sorted = day_cols_sorted[: int(forecast_horizon)]

    # Iterate rows with stable field access
    for row in df.itertuples(index=False):
        ticker = str(getattr(row, "Ticker", "")).strip()
        model = str(getattr(row, "Model", "")).strip()
        regressor = str(getattr(row, "Regressor", "")).strip()

        if not ticker or not model or not regressor:
            log.warning("Skipping exo config row with empty Ticker/Model/Regressor: %s", row)
            continue

        enabled = _parse_bool(getattr(row, "Enabled", ""))
        scenario_mode_raw = getattr(row, "ScenarioMode", "")
        scenario_mode = _parse_scenario_mode(scenario_mode_raw)
        if scenario_mode is None:
            log.warning(
                "Invalid ScenarioMode '%s' for %s/%s/%s. Skipping row.",
                scenario_mode_raw,
                ticker,
                model,
                regressor,
            )
            continue

        values: List[Optional[float]] = []
        for day_col in day_cols_sorted:
            raw_val = getattr(row, day_col, None)
            f = _to_float_or_none(raw_val)
            if raw_val is not None and f is None and not (isinstance(raw_val, float) and pd.isna(raw_val)):
                # Only warn when an explicit non-empty non-numeric value was present
                if isinstance(raw_val, str) and not raw_val.strip():
                    pass
                else:
                    log.warning(
                        "Non-numeric/unsupported value '%s' in '%s' for %s/%s/%s. Treating as None.",
                        raw_val,
                        day_col,
                        ticker,
                        model,
                        regressor,
                    )
            values.append(f)

        values = _strip_trailing_nones(values)

        if model not in cfg:
            cfg[model] = {}
        if ticker not in cfg[model]:
            cfg[model][ticker] = {}

        cfg[model][ticker][regressor] = {
            "enabled": bool(enabled),
            "scenario_mode": cast(str, scenario_mode),
            "values": values,
        }

    log.info("Loaded exogenous configuration from %s: %d models configured.", path, len(cfg))
    return cfg


def get_exog_config(config: ExoConfigType, model: str, ticker: str, regressor: str) -> Optional[Dict[str, Any]]:
    """Return config dict for a specific (model, ticker, regressor) or None."""
    m = str(model).strip()
    t = str(ticker).strip()
    r = str(regressor).strip()
    try:
        return config[m][t][r]
    except KeyError:
        return None


def get_enabled_regressors(config: ExoConfigType, model: str, ticker: str) -> List[str]:
    """Return all enabled regressor names for a given (model, ticker)."""
    m = str(model).strip()
    t = str(ticker).strip()

    if m not in config or t not in config[m]:
        return []

    enabled: List[str] = []
    for reg_name, spec in config[m][t].items():
        if bool(spec.get("enabled", False)):
            enabled.append(str(reg_name))
    return enabled


def get_exog_spec(config: ExoConfigType, model: str, ticker: str, regressor: str) -> Optional[ExoSpec]:
    """
    Typed wrapper around get_exog_config() returning an ExoSpec dataclass.

    This is non-breaking (legacy code can keep using dicts), but refactored code
    can prefer a typed interface.
    """
    d = get_exog_config(config, model, ticker, regressor)
    if not d:
        return None
    return ExoSpec(
        enabled=bool(d.get("enabled", False)),
        scenario_mode=str(d.get("scenario_mode", "NONE")).upper(),
        values=list(cast(List[Optional[float]], d.get("values", []))),
    )


__all__ = [
    "ExoConfigType",
    "ExoSpec",
    "load_exo_config",
    "get_exog_config",
    "get_enabled_regressors",
    "get_exog_spec",
]
