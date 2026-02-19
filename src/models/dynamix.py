from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, cast

import numpy as np
import pandas as pd

from src.config import paths

log = logging.getLogger(__name__)

DEFAULT_FH = 3
DEFAULT_TARGET_COL = "Close"


@dataclass(frozen=True)
class DynaMixResult:
    model_used: str
    cols_used: Sequence[str]
    pred_df: pd.DataFrame
    pred_col: str = "DYNAMIX_Pred"
    lower_col: str = "DYNAMIX_Lower"
    upper_col: str = "DYNAMIX_Upper"
    meta: Dict[str, Any] = field(default_factory=dict)


def _discover_fh() -> int:
    try:
        import Constants as C  # type: ignore

        fh = int(getattr(C, "FH", DEFAULT_FH))
        return fh if fh > 0 else DEFAULT_FH
    except Exception:
        return DEFAULT_FH


def _discover_target_col() -> str:
    try:
        import Constants as C  # type: ignore

        return str(getattr(C, "TARGET_COL", DEFAULT_TARGET_COL))
    except Exception:
        return DEFAULT_TARGET_COL


def _discover_bool(name: str, default: bool) -> bool:
    try:
        import Constants as C  # type: ignore

        return bool(getattr(C, name, default))
    except Exception:
        return default


def _discover_int(name: str, default: int) -> int:
    try:
        import Constants as C  # type: ignore

        return int(getattr(C, name, default))
    except Exception:
        return int(default)


def _discover_str(name: str, default: str) -> str:
    try:
        import Constants as C  # type: ignore

        v = str(getattr(C, name, default)).strip()
        return v if v else default
    except Exception:
        return default


def _discover_dynamix_repo_path() -> Path:
    # Best effort: load repo-root .env so FIN_DYNAMIX_REPO works in non-app3G entrypoints.
    try:
        paths.load_dotenv_if_present()
    except Exception:
        pass

    def _is_repo(p: Path) -> bool:
        try:
            return p.exists() and (p / "src" / "model" / "forecaster.py").exists()
        except Exception:
            return False

    def _scan_candidates() -> Optional[Path]:
        roots = [paths.APP_ROOT, paths.APP_ROOT / "vendor", paths.APP_ROOT.parent]
        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            try:
                for child in root.iterdir():
                    if not child.is_dir():
                        continue
                    nm = child.name.lower()
                    if "dynamix" in nm and _is_repo(child):
                        return child.resolve()
            except Exception:
                continue
        return None

    env_override = os.environ.get("FIN_DYNAMIX_REPO", "").strip()
    if env_override:
        env_path = Path(env_override).resolve()
        if _is_repo(env_path):
            return env_path
        log.warning(
            "DynaMix: FIN_DYNAMIX_REPO is set but path does not exist: %s", env_path
        )

    cfg_path = _discover_str("DYNAMIX_REPO_PATH", "")
    if cfg_path:
        cfg_repo = Path(cfg_path).resolve()
        if _is_repo(cfg_repo):
            return cfg_repo
        log.info(
            "DynaMix: DYNAMIX_REPO_PATH does not exist (%s). Trying defaults.",
            cfg_repo,
        )

    vendor_default = (paths.APP_ROOT / "vendor" / "DynaMix-python").resolve()
    if vendor_default.exists():
        return vendor_default

    repo_root_default = (paths.APP_ROOT / "DynaMix-python").resolve()
    if _is_repo(repo_root_default):
        return repo_root_default

    scanned = _scan_candidates()
    if scanned is not None:
        return scanned

    return vendor_default


def _resolve_worker_python() -> str:
    env_override = os.environ.get("FIN_DYNAMIX_PY_EXE", "").strip()
    if env_override and os.path.exists(env_override):
        return env_override

    cfg_path = _discover_str("DYNAMIX_WORKER_PY_EXE", "")
    if cfg_path and os.path.exists(cfg_path):
        return cfg_path

    return sys.executable


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        out = cast(pd.DataFrame, df.copy())
        out.index = pd.to_datetime(out.index, errors="coerce")
    else:
        out = cast(pd.DataFrame, df.copy())

    out = cast(pd.DataFrame, out.loc[~out.index.isna(), :].copy())
    if out.empty:
        raise ValueError(
            "DynaMix: DataFrame became empty after DatetimeIndex coercion."
        )

    if out.index.duplicated().any():
        out = cast(pd.DataFrame, out.loc[~out.index.duplicated(keep="last"), :].copy())

    if not out.index.is_monotonic_increasing:
        out = cast(pd.DataFrame, out.sort_index())

    return out


def _write_context_csv(series: pd.Series, out_path: Path, *, target_col: str) -> None:
    context_df = pd.DataFrame(
        {"Date": series.index, target_col: series.to_numpy(dtype=float)}
    )
    context_df.to_csv(out_path, index=False)


def _build_worker_env(repo_path: Optional[Path]) -> Dict[str, str]:
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = ""
    env["FIN_DYNAMIX_FORCE_CPU"] = "1"
    if repo_path is not None and repo_path.exists():
        env["FIN_DYNAMIX_REPO"] = str(repo_path)
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    return env


def _parse_worker_payload(stdout: str) -> Optional[Dict[str, Any]]:
    lines = [ln.strip() for ln in str(stdout or "").splitlines() if ln.strip()]
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and "ok" in obj:
            return cast(Dict[str, Any], obj)
    return None


def _read_artifact_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None

    df = pd.read_csv(path)
    if df.empty:
        return None

    date_col = "Date" if "Date" in df.columns else str(df.columns[0])
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = cast(pd.DataFrame, df.dropna(subset=[date_col]))
    if df.empty:
        return None

    df = cast(pd.DataFrame, df.set_index(date_col))
    if not isinstance(df.index, pd.DatetimeIndex):
        return None

    df = cast(pd.DataFrame, df.sort_index())
    return df


def _normalize_forecast_df(df: pd.DataFrame, *, fh: int) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None

    out = cast(pd.DataFrame, df.copy())

    pred_col = "DYNAMIX_Pred"
    if pred_col not in out.columns:
        numeric_cols = [c for c in out.columns if pd.api.types.is_numeric_dtype(out[c])]
        if not numeric_cols:
            return None
        out = cast(pd.DataFrame, out.rename(columns={numeric_cols[0]: pred_col}))

    out[pred_col] = pd.to_numeric(out[pred_col], errors="coerce")
    out = cast(pd.DataFrame, out.dropna(subset=[pred_col]))
    if out.empty:
        return None

    out = cast(pd.DataFrame, out.iloc[: int(fh)].copy())
    if len(out) < int(fh):
        return None

    if "DYNAMIX_Lower" not in out.columns:
        out["DYNAMIX_Lower"] = np.nan
    if "DYNAMIX_Upper" not in out.columns:
        out["DYNAMIX_Upper"] = np.nan

    out["DYNAMIX_Lower"] = pd.to_numeric(out["DYNAMIX_Lower"], errors="coerce")
    out["DYNAMIX_Upper"] = pd.to_numeric(out["DYNAMIX_Upper"], errors="coerce")

    return cast(
        pd.DataFrame, out[["DYNAMIX_Pred", "DYNAMIX_Lower", "DYNAMIX_Upper"]].copy()
    )


def predict_dynamix(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: Optional[str] = None,
    fh: Optional[int] = None,
    dynamix_repo_path: Optional[str] = None,
    timeout_s: Optional[int] = None,
    standardize: Optional[bool] = None,
    fit_nonstationary: Optional[bool] = None,
    preprocessing_method: Optional[str] = None,
    context_steps: Optional[int] = None,
) -> Optional[pd.DataFrame]:
    """
    Run DynaMix forecasting through a dedicated worker process.

    CPU-only behavior is always enforced via worker environment and arguments.
    Returns a DataFrame with columns DYNAMIX_Pred/DYNAMIX_Lower/DYNAMIX_Upper.
    """
    if not _discover_bool("DYNAMIX_ENABLED", True):
        return None

    if enriched_data is None or enriched_data.empty:
        return None

    fh_i = int(fh) if fh is not None else _discover_fh()
    if fh_i <= 0:
        fh_i = DEFAULT_FH

    tgt = str(target_col) if target_col else _discover_target_col()
    if tgt not in enriched_data.columns:
        log.warning(
            "DynaMix: target column '%s' not found for %s.", tgt, ticker or "<ticker>"
        )
        return None

    try:
        df = _ensure_datetime_index(enriched_data)
    except Exception as e:
        log.warning(
            "DynaMix: invalid datetime index for %s: %s", ticker or "<ticker>", e
        )
        return None

    y = cast(pd.Series, pd.to_numeric(df[tgt], errors="coerce")).dropna()
    if y.empty:
        return None

    y = cast(pd.Series, y.asfreq("B").ffill().dropna())

    min_len = _discover_int("DYNAMIX_MIN_DATA_LENGTH", 30)
    if len(y) < max(2, min_len):
        log.warning(
            "DynaMix: insufficient data length (%d) for %s. Need >= %d.",
            len(y),
            ticker or "<ticker>",
            max(2, min_len),
        )
        return None

    ctx_steps = (
        int(context_steps)
        if context_steps is not None
        else _discover_int("DYNAMIX_CONTEXT_STEPS", 2048)
    )
    if ctx_steps > 0 and len(y) > ctx_steps:
        y = cast(pd.Series, y.iloc[-ctx_steps:])

    std_flag = (
        bool(standardize)
        if standardize is not None
        else _discover_bool("DYNAMIX_STANDARDIZE", True)
    )
    nonstat_flag = (
        bool(fit_nonstationary)
        if fit_nonstationary is not None
        else _discover_bool("DYNAMIX_FIT_NONSTATIONARY", False)
    )
    prep = (
        str(preprocessing_method)
        if preprocessing_method
        else _discover_str("DYNAMIX_PREPROCESSING_METHOD", "pos_embedding")
    )

    timeout_i = (
        int(timeout_s)
        if timeout_s is not None
        else _discover_int("DYNAMIX_TIMEOUT_SEC", 300)
    )
    timeout_i = max(30, timeout_i)

    repo_path: Optional[Path]
    if dynamix_repo_path:
        rp = Path(dynamix_repo_path).resolve()
        if rp.exists():
            repo_path = rp
        else:
            log.info(
                "DynaMix: explicit repo path does not exist (%s). Falling back to auto-discovery.",
                rp,
            )
            repo_path = _discover_dynamix_repo_path()
    else:
        repo_path = _discover_dynamix_repo_path()

    repo_arg = str(repo_path) if (repo_path is not None and repo_path.exists()) else ""
    if not repo_arg:
        log.warning(
            "DynaMix: no valid repository path resolved for %s. "
            "Set FIN_DYNAMIX_REPO or DYNAMIX_REPO_PATH to a clone containing src/model/forecaster.py.",
            ticker or "<ticker>",
        )
    worker_py = _resolve_worker_python()

    try:
        worker_script = paths.get_worker_script_path("dynamix_worker.py")
    except Exception as e:
        log.warning("DynaMix: worker script resolution failed: %s", e)
        return None

    with tempfile.TemporaryDirectory(prefix="fin_dynamix_") as tmp_dir:
        td = Path(tmp_dir)
        context_csv = td / "context.csv"
        artifact_csv = td / "forecast.csv"

        try:
            _write_context_csv(y, context_csv, target_col=tgt)
        except Exception as e:
            log.warning("DynaMix: failed writing context CSV: %s", e)
            return None

        cmd = [
            worker_py,
            str(worker_script),
            "--ticker",
            str(ticker or "UNKNOWN"),
            "--context-csv",
            str(context_csv),
            "--target-col",
            str(tgt),
            "--fh",
            str(int(fh_i)),
            "--artifact-csv",
            str(artifact_csv),
            "--dynamix-repo",
            repo_arg,
            "--context-steps",
            str(int(ctx_steps)),
            "--preprocessing-method",
            str(prep),
            "--standardize",
            "1" if std_flag else "0",
            "--fit-nonstationary",
            "1" if nonstat_flag else "0",
        ]

        env = _build_worker_env(repo_path)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=int(timeout_i),
                cwd=str(paths.APP_ROOT),
                env=env,
            )
        except subprocess.TimeoutExpired:
            log.warning(
                "DynaMix: worker timeout for %s after %ss.",
                ticker or "<ticker>",
                timeout_i,
            )
            return None
        except Exception as e:
            log.warning(
                "DynaMix: worker invocation failed for %s: %s",
                ticker or "<ticker>",
                e,
                exc_info=True,
            )
            return None

        payload = _parse_worker_payload(proc.stdout)
        if payload is None:
            stderr_tail = (proc.stderr or "").strip()[-1500:]
            log.warning(
                "DynaMix: worker returned invalid protocol for %s (rc=%s). stderr(tail)=%s",
                ticker or "<ticker>",
                proc.returncode,
                stderr_tail,
            )
            return None

        if not bool(payload.get("ok", False)):
            err = payload.get("error", {})
            msg = (
                err.get("message", "unknown worker error")
                if isinstance(err, dict)
                else str(err)
            )
            log.warning(
                "DynaMix: worker failed for %s (rc=%s): %s",
                ticker or "<ticker>",
                proc.returncode,
                msg,
            )
            return None

        artifact_path = payload.get("artifact_csv")
        art = Path(str(artifact_path)).resolve() if artifact_path else artifact_csv

        out_raw = _read_artifact_csv(art)
        if out_raw is None:
            log.warning(
                "DynaMix: worker output CSV missing/unreadable for %s: %s",
                ticker or "<ticker>",
                art,
            )
            return None

        out = _normalize_forecast_df(out_raw, fh=fh_i)
        if out is None:
            log.warning(
                "DynaMix: worker output normalization failed for %s.",
                ticker or "<ticker>",
            )
            return None

        return out


def predict_dynamix_result(
    enriched_data: pd.DataFrame,
    *,
    ticker: str = "",
    target_col: Optional[str] = None,
    fh: Optional[int] = None,
    dynamix_repo_path: Optional[str] = None,
) -> Optional[DynaMixResult]:
    pred_df = predict_dynamix(
        enriched_data,
        ticker=ticker,
        target_col=target_col,
        fh=fh,
        dynamix_repo_path=dynamix_repo_path,
    )
    if pred_df is None or pred_df.empty:
        return None

    tgt = str(target_col) if target_col else _discover_target_col()
    fh_i = int(fh) if fh is not None else _discover_fh()

    return DynaMixResult(
        model_used="DYNAMIX",
        cols_used=(tgt,),
        pred_df=pred_df,
        meta={
            "ticker": ticker,
            "target_col": tgt,
            "fh": int(fh_i),
            "cpu_only": True,
            "repo_path": str(_discover_dynamix_repo_path()),
        },
    )


__all__ = ["DynaMixResult", "predict_dynamix", "predict_dynamix_result"]
