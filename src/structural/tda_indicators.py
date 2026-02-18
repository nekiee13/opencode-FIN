# ------------------------
# src\structural\tda_indicators.py
# ------------------------
"""
TDA Phase 2A structural indicators (CPI-aligned export surface).

CPI alignment objectives
- Defaults:
  - window_len_returns = 60
  - embed_m = 3
  - embed_tau = 1
  - persist_threshold = 0.5
  - lastn_windows = 10
- States:
  - OK, MISSING_DEP, INSUFFICIENT_DATA, DEGENERATE, ERROR
  - Legacy aliases retained (DISABLED->MISSING_DEP, FAILED->ERROR)
- Metrics (CPI-required columns):
  - H1_MaxPersistence
  - H1_CountAbove_Thr
  - H1_Entropy
- Optional dependency gating:
  - ripser is imported lazily; missing ripser yields MISSING_DEP and no crash.

Corrections applied
- Pylance: helper functions accept Optional[DataFrame] and always return DataFrame.
- Pylance: delegated metrics return is always coerced to pd.DataFrame(...).
- Pylance: _to_returns uses pandas Series diff (avoid NDArray .diff confusion).
- CPI: State rendering uses Enum.value (avoid "TDAState.OK" strings).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from collections.abc import Callable

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Defaults (exported for scripts/tda_export.py CLI defaults)
# ----------------------------------------------------------------------

DEFAULT_WINDOW_LEN = 60
DEFAULT_EMBED_M = 3
DEFAULT_EMBED_TAU = 1
DEFAULT_PERSIST_THR = 0.5
DEFAULT_LASTN = 10


# ----------------------------------------------------------------------
# State + context objects (export surface)
# ----------------------------------------------------------------------


class TDAState(str, Enum):
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    MISSING_DEP = "MISSING_DEP"
    DEGENERATE = "DEGENERATE"
    ERROR = "ERROR"

    # Legacy aliases (kept for backward compatibility)
    DISABLED = "MISSING_DEP"  # alias
    FAILED = "ERROR"  # alias


@dataclass
class TickerTDAContext:
    """
    Phase 2A context object that exporter can render safely.
    """

    ticker: str
    asof: pd.Timestamp
    window_len: int
    embed_m: int
    embed_tau: int
    persist_thr: float
    lastn: int
    state: Any = TDAState.MISSING_DEP

    # core diagnostics
    n_obs: int = 0
    n_embed: int = 0
    ret_vol: float = float("nan")

    # legacy metrics retained
    h0_max_persist: float = float("nan")
    h1_max_persist: float = float("nan")
    h1_sum_persist: float = float("nan")
    h1_entropy_proxy: float = float("nan")

    # CPI-required metrics
    h1_count_above_thr: float = float("nan")
    h1_entropy: float = float("nan")

    # interpretations
    h1_label: str = "UNKNOWN"
    cycle_note: str = ""
    provenance: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# Small formatting helpers (stable exporter surface)
# ----------------------------------------------------------------------


def _state_to_str(state: Any) -> str:
    """
    CPI requirement:
    - State strings must be in {OK, MISSING_DEP, INSUFFICIENT_DATA, DEGENERATE, ERROR}.
    - Enum members must be rendered via .value, not via str(EnumMember).
    """
    try:
        if isinstance(state, Enum):
            return str(getattr(state, "value", str(state)))
    except Exception:
        pass
    return str(state)


# ----------------------------------------------------------------------
# Optional dependency gating (ripser)
# ----------------------------------------------------------------------


def _get_ripser_func() -> Optional[Callable[..., Any]]:
    """
    Lazy retrieval of ripser callable.

    Order:
    1) src.utils.compat.ripser if present
    2) direct import from ripser package

    Returns
    - callable or None
    """
    try:
        from src.utils import compat  # type: ignore

        f = getattr(compat, "ripser", None)
        if callable(f):
            return cast(Callable[..., Any], f)
    except Exception:
        pass

    try:
        from ripser import ripser  # type: ignore

        return cast(Callable[..., Any], ripser)
    except Exception:
        return None


def _tda_enabled() -> bool:
    """
    Feature gate for TDA computation.

    CPI intent:
    - HAS_TDA implies numpy+pandas+ripser are available.
    - If HAS_TDA is absent, fallback is ripser callable presence.
    """
    try:
        from src.utils import compat  # type: ignore

        if bool(getattr(compat, "HAS_TDA", False)):
            return True
    except Exception:
        pass

    return _get_ripser_func() is not None


# ----------------------------------------------------------------------
# Optional legacy delegation (disabled by default for CPI stability)
# ----------------------------------------------------------------------


def _try_delegate_to_compat() -> Optional[Any]:
    """
    Optional legacy delegation for backward parity.

    Default behavior:
    - Disabled unless FIN_ALLOW_COMPAT_TDA_DELEGATION=1 is set.
    """
    if os.environ.get("FIN_ALLOW_COMPAT_TDA_DELEGATION", "").strip() != "1":
        return None

    try:
        import TDAIndicators as m  # type: ignore

        required = (
            "compute_tda_context",
            "build_tda_context_markdown",
            "build_tda_metrics_df",
            "TDAState",
            "TickerTDAContext",
        )
        if all(hasattr(m, k) for k in required):
            return m
        return None
    except Exception:
        return None


_COMPAT_TDA = _try_delegate_to_compat()


# ----------------------------------------------------------------------
# Core math helpers
# ----------------------------------------------------------------------


def _ensure_datetime_index(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """
    Normalize index to DatetimeIndex, drop invalid timestamps, enforce monotonic increase.

    Returns
    - DataFrame (never None; never Series)
    """
    if df is None:
        return pd.DataFrame()
    if df.empty:
        return cast(pd.DataFrame, df.copy())

    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")

    out = out.loc[~out.index.isna()].copy()

    if out.index.duplicated().any():
        out = out[~out.index.duplicated(keep="last")]

    if not out.index.is_monotonic_increasing:
        out = out.sort_index()

    return cast(pd.DataFrame, out)


def _as_bday(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """
    Normalize to business-day frequency.

    Returns
    - DataFrame (never None; never Series)
    """
    if df is None:
        return pd.DataFrame()
    if df.empty:
        return cast(pd.DataFrame, df.copy())

    out = df.asfreq("B").ffill()
    return cast(pd.DataFrame, out)


def _to_returns(close: pd.Series) -> pd.Series:
    """
    Compute log returns as a pandas Series.
    """
    s = pd.to_numeric(close, errors="coerce")
    s = cast(pd.Series, s).dropna()
    if len(s) < 3:
        return cast(pd.Series, s.iloc[0:0])

    s_log = pd.Series(np.log(s.to_numpy(dtype=float)), index=s.index)
    r = s_log.diff()
    r = cast(pd.Series, r).dropna()
    return r


def _delay_embed_forward(x: np.ndarray, m: int, tau: int) -> np.ndarray:
    """
    Delay embedding (forward form):
      row i = [x_i, x_{i+tau}, x_{i+2tau}, ..., x_{i+(m-1)tau}]
    Shape: (n - (m-1)*tau, m)
    """
    arr = np.asarray(x, dtype=float)
    n = int(arr.size)
    if m <= 1:
        return arr.reshape(-1, 1)
    if tau <= 0:
        tau = 1

    out_len = n - (m - 1) * tau
    if out_len <= 0:
        return np.empty((0, m), dtype=float)

    emb = np.empty((out_len, m), dtype=float)
    for j in range(m):
        emb[:, j] = arr[j * tau : j * tau + out_len]
    return emb


def _finite_diag_persist(diag: Any) -> np.ndarray:
    """
    Extract finite persistence lifetimes from an H_k diagram-like object.

    Accepts
    - list-like, ndarray, or empty/None
    Returns
    - 1D ndarray of lifetimes (positive only)
    """
    if diag is None:
        return np.asarray([], dtype=float)

    d = np.asarray(diag, dtype=float)
    if d.size == 0:
        return np.asarray([], dtype=float)
    if d.ndim != 2 or d.shape[1] != 2:
        return np.asarray([], dtype=float)

    b = d[:, 0]
    e = d[:, 1]
    mask = np.isfinite(b) & np.isfinite(e) & (e >= b)

    p = (e[mask] - b[mask]).astype(float)
    p = p[np.isfinite(p)]
    p = p[p > 0.0]
    return p


def _persistence_entropy(persist: np.ndarray) -> float:
    """
    Persistence entropy over normalized lifetimes (natural log).
    """
    p = np.asarray(persist, dtype=float)
    p = p[np.isfinite(p)]
    p = p[p > 0.0]
    if p.size == 0:
        return 0.0

    s = float(np.sum(p))
    if not np.isfinite(s) or s <= 0.0:
        return 0.0

    w = p / s
    w = w[w > 0.0]
    if w.size == 0:
        return 0.0

    return float(-np.sum(w * np.log(w)))


def _truncate_error_message(msg: str, max_len: int = 240) -> str:
    s = str(msg or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."


def _label_h1(h1_max: float, persist_thr: float) -> str:
    if not np.isfinite(h1_max):
        return "UNKNOWN"
    if h1_max >= max(1.5 * persist_thr, persist_thr + 1e-12):
        return "H1_STRONG"
    if h1_max >= persist_thr:
        return "H1_WEAK"
    return "H1_NONE"


# ----------------------------------------------------------------------
# Internal compute (authoritative CPI-aligned implementation)
# ----------------------------------------------------------------------


def _compute_one_ticker(
    ticker: str,
    df: pd.DataFrame,
    *,
    window_len: int,
    embed_m: int,
    embed_tau: int,
    persist_thr: float,
    lastn: int,
) -> TickerTDAContext:
    dfn = _ensure_datetime_index(df)
    dfn = _as_bday(dfn)

    asof = (
        pd.Timestamp(dfn.index.max()) if not dfn.empty else pd.Timestamp("1970-01-01")
    )
    ctx = TickerTDAContext(
        ticker=str(ticker),
        asof=asof,
        window_len=int(window_len),
        embed_m=int(embed_m),
        embed_tau=int(embed_tau),
        persist_thr=float(persist_thr),
        lastn=int(lastn),
        state=TDAState.MISSING_DEP,
    )

    if dfn.empty or "Close" not in dfn.columns:
        ctx.state = TDAState.INSUFFICIENT_DATA
        ctx.notes.append("Missing data or Close column.")
        return ctx

    r = _to_returns(cast(pd.Series, dfn["Close"]))
    if r.empty:
        ctx.state = TDAState.INSUFFICIENT_DATA
        ctx.notes.append("Insufficient Close history to compute returns.")
        return ctx

    r = r.iloc[-int(window_len) :] if len(r) > int(window_len) else r
    ctx.n_obs = int(len(r))
    ctx.ret_vol = (
        float(np.std(r.to_numpy(dtype=float), ddof=1)) if len(r) > 1 else float("nan")
    )

    min_needed = max(20, 2 * int(embed_m) * int(embed_tau))
    if ctx.n_obs < min_needed:
        ctx.state = TDAState.INSUFFICIENT_DATA
        ctx.notes.append(
            f"Insufficient returns for embedding. n_obs={ctx.n_obs}, min_needed={min_needed}."
        )
        return ctx

    ripser = _get_ripser_func()
    if not _tda_enabled() or ripser is None:
        ctx.state = TDAState.MISSING_DEP
        ctx.notes.append("ripser not available; TDA disabled by dependency gating.")
        return ctx

    x = r.to_numpy(dtype=float)
    x = x[np.isfinite(x)]
    if x.size < min_needed:
        ctx.state = TDAState.INSUFFICIENT_DATA
        ctx.notes.append("Too few finite return points after cleaning.")
        return ctx

    emb = _delay_embed_forward(x, m=int(embed_m), tau=int(embed_tau))
    if emb.size == 0 or emb.shape[0] < 15:
        ctx.state = TDAState.INSUFFICIENT_DATA
        ctx.notes.append(
            f"Delay embedding too short (n_embed={emb.shape[0] if emb.ndim == 2 else 0})."
        )
        return ctx

    ctx.n_embed = int(emb.shape[0])

    try:
        mu = np.mean(emb, axis=0)
        sd = np.std(emb, axis=0, ddof=1)
        if np.any(~np.isfinite(sd)) or np.any(sd <= 0.0):
            ctx.state = TDAState.DEGENERATE
            ctx.notes.append(
                "Degenerate embedding: zero/invalid variance in at least one dimension."
            )
            return ctx
        emb_z = (emb - mu) / sd
    except Exception:
        ctx.state = TDAState.DEGENERATE
        ctx.notes.append("Degenerate embedding: standardization failed.")
        return ctx

    try:
        out = ripser(emb_z, maxdim=1)  # type: ignore[misc]
        dgms = cast(Any, out).get("dgms", [])

        d0 = dgms[0] if len(dgms) > 0 else np.asarray([], dtype=float)
        d1 = dgms[1] if len(dgms) > 1 else np.asarray([], dtype=float)

        p0 = _finite_diag_persist(d0)
        p1 = _finite_diag_persist(d1)

        ctx.h0_max_persist = float(np.max(p0)) if p0.size else float("nan")

        h1_max = float(np.max(p1)) if p1.size else 0.0
        h1_count = float(np.sum(p1 >= float(persist_thr))) if p1.size else 0.0
        h1_entropy = _persistence_entropy(p1)

        ctx.h1_max_persist = h1_max
        ctx.h1_sum_persist = float(np.sum(p1)) if p1.size else 0.0
        ctx.h1_count_above_thr = h1_count
        ctx.h1_entropy = float(h1_entropy) if np.isfinite(h1_entropy) else float("nan")
        ctx.h1_entropy_proxy = ctx.h1_entropy

        ctx.h1_label = _label_h1(ctx.h1_max_persist, float(persist_thr))

        if ctx.h1_label == "H1_STRONG":
            ctx.cycle_note = f"Strong H1 persistence (max≈{ctx.h1_max_persist:.3f}) suggests stable cyclic structure."
        elif ctx.h1_label == "H1_WEAK":
            ctx.cycle_note = f"Weak H1 persistence (max≈{ctx.h1_max_persist:.3f}) suggests tentative cyclic structure."
        elif ctx.h1_label == "H1_NONE":
            ctx.cycle_note = f"No meaningful H1 persistence above threshold (thr={float(persist_thr):.3f})."
        else:
            ctx.cycle_note = "H1 persistence unavailable."

        ctx.state = TDAState.OK
        ctx.provenance = {
            "input": "OHLCV (Close -> log returns)",
            "embedding": f"delay(m={int(embed_m)}, tau={int(embed_tau)}) over last {ctx.n_obs} returns",
            "ph": "ripser(maxdim=1) on standardized embedding",
            "phase": "Phase 2A (H1-only persistence summary)",
        }
        return ctx

    except Exception as e:
        ctx.state = TDAState.ERROR
        short = _truncate_error_message(f"{type(e).__name__}: {e}")
        ctx.notes.append(f"TDA compute failed: {short}")
        return ctx


# ----------------------------------------------------------------------
# Public API expected by scripts/tda_export.py
# ----------------------------------------------------------------------


def compute_tda_for_ticker(*args: Any, **kwargs: Any) -> TickerTDAContext:
    """
    Legacy-friendly single-ticker adapter.

    Accepted calling styles:
    - compute_tda_for_ticker(ticker, df_or_close, ...)
    - compute_tda_for_ticker(df_or_close, ticker, ...)
    - compute_tda_for_ticker(ticker="AAA", df_close=df, ...)

    Returns
    - TickerTDAContext for one ticker.
    """
    ticker: str = str(kwargs.pop("ticker", "")).strip()
    payload: Any = kwargs.pop("df_close", None)
    if payload is None:
        payload = kwargs.pop("df", None)
    if payload is None:
        payload = kwargs.pop("close", None)

    if len(args) >= 2:
        a0, a1 = args[0], args[1]
        if isinstance(a0, str):
            ticker = str(a0)
            payload = a1
        elif isinstance(a1, str):
            payload = a0
            ticker = str(a1)
    elif len(args) == 1 and payload is None:
        if isinstance(args[0], str):
            ticker = str(args[0])
        else:
            payload = args[0]

    if not ticker:
        ticker = "UNKNOWN"

    if isinstance(payload, pd.Series):
        df_one = pd.DataFrame(
            {"Close": pd.to_numeric(payload, errors="coerce")}, index=payload.index
        )
    elif isinstance(payload, pd.DataFrame):
        df_one = payload.copy()
        if "Close" not in df_one.columns and len(df_one.columns) == 1:
            only_col = str(df_one.columns[0])
            df_one = df_one.rename(columns={only_col: "Close"})
    else:
        df_one = pd.DataFrame({"Close": pd.Series(dtype=float)})

    window_len = int(kwargs.pop("window_len", DEFAULT_WINDOW_LEN))
    embed_m = int(kwargs.pop("embed_m", DEFAULT_EMBED_M))
    embed_tau = int(kwargs.pop("embed_tau", DEFAULT_EMBED_TAU))
    persist_thr = float(kwargs.pop("persist_thr", DEFAULT_PERSIST_THR))
    lastn = int(kwargs.pop("lastn", DEFAULT_LASTN))

    ctx = _compute_one_ticker(
        ticker,
        df_one,
        window_len=window_len,
        embed_m=embed_m,
        embed_tau=embed_tau,
        persist_thr=persist_thr,
        lastn=lastn,
    )

    asof_override = kwargs.pop("asof", kwargs.pop("asof_date", None))
    if asof_override is not None:
        try:
            ctx.asof = pd.Timestamp(asof_override)
        except Exception:
            pass

    return ctx


def compute_tda_context(
    ticker_dfs: Dict[str, pd.DataFrame],
    *,
    asof_policy: str = "min_across_tickers",
    window_len: int = DEFAULT_WINDOW_LEN,
    embed_m: int = DEFAULT_EMBED_M,
    embed_tau: int = DEFAULT_EMBED_TAU,
    persist_thr: float = DEFAULT_PERSIST_THR,
    lastn: int = DEFAULT_LASTN,
) -> Tuple[List[TickerTDAContext], str, pd.DataFrame]:
    """
    Returns
    - contexts: list[TickerTDAContext]
    - markdown: TDA_CONTEXT markdown block
    - metrics_df: DataFrame containing CPI-required columns
    """
    if _COMPAT_TDA is not None:
        try:
            c_out, md_out, df_out = _COMPAT_TDA.compute_tda_context(  # type: ignore[attr-defined]
                ticker_dfs,
                asof_policy=asof_policy,
                window_len=window_len,
                embed_m=embed_m,
                embed_tau=embed_tau,
                persist_thr=persist_thr,
                lastn=lastn,
            )
            contexts = cast(List[TickerTDAContext], c_out)
            md = cast(str, md_out)
            metrics_df = pd.DataFrame(df_out)
            return contexts, md, metrics_df
        except Exception as e:
            log.warning(
                "compat TDAIndicators delegation failed; falling back to src.structural.tda_indicators. Error: %s",
                e,
                exc_info=True,
            )

    contexts: List[TickerTDAContext] = []
    for t, df in ticker_dfs.items():
        contexts.append(
            _compute_one_ticker(
                str(t),
                df,
                window_len=int(window_len),
                embed_m=int(embed_m),
                embed_tau=int(embed_tau),
                persist_thr=float(persist_thr),
                lastn=int(lastn),
            )
        )

    if contexts:
        if asof_policy == "min_across_tickers":
            global_asof = min(pd.Timestamp(c.asof) for c in contexts)
        else:
            global_asof = max(pd.Timestamp(c.asof) for c in contexts)
    else:
        global_asof = pd.Timestamp("1970-01-01")

    md = build_tda_context_markdown(
        contexts,
        global_asof=global_asof,
        title="TDA_CONTEXT (Phase 2A — H1 cycles from return embeddings)",
    )
    metrics = build_tda_metrics_df(contexts, global_asof=global_asof)
    return contexts, md, metrics


def build_tda_context_markdown(
    contexts: Sequence[TickerTDAContext],
    *,
    global_asof: pd.Timestamp,
    title: str = "TDA_CONTEXT (Phase 2A — H1 cycles from return embeddings)",
) -> str:
    if _COMPAT_TDA is not None and hasattr(_COMPAT_TDA, "build_tda_context_markdown"):
        try:
            md_out = _COMPAT_TDA.build_tda_context_markdown(  # type: ignore[attr-defined]
                contexts,
                global_asof=global_asof,
                title=title,
            )
            return cast(str, md_out)
        except Exception:
            pass

    ga = pd.Timestamp(global_asof).strftime("%Y-%m-%d")
    lines: List[str] = []
    lines.append(f"{title} (Computed from OHLCV; no web citations)")
    lines.append("")
    lines.append(f"As-of (global): {ga}")
    lines.append(
        "Method: Close -> log returns; delay embedding; persistent homology via ripser (maxdim=1)."
    )
    lines.append("Outputs: H1_MaxPersistence, H1_CountAbove_Thr, H1_Entropy.")
    lines.append("")

    for c in contexts:
        asof_s = pd.Timestamp(c.asof).strftime("%Y-%m-%d") if pd.notna(c.asof) else "NA"
        lines.append(f"[{c.ticker}]")
        lines.append(f"State: {_state_to_str(getattr(c, 'state', ''))}")
        lines.append(f"AsOf:  {asof_s}")
        lines.append("Params:")
        lines.append(f"  window_len: {c.window_len}")
        lines.append(f"  embed_m: {c.embed_m}")
        lines.append(f"  embed_tau: {c.embed_tau}")
        lines.append(f"  persist_thr: {c.persist_thr:.3f}")
        lines.append(f"  lastn: {c.lastn}")
        lines.append("Stats:")
        lines.append(f"  n_obs_returns: {c.n_obs}")
        lines.append(f"  n_embed_points: {c.n_embed}")
        lines.append(
            f"  ret_vol: {c.ret_vol:.6f}" if np.isfinite(c.ret_vol) else "  ret_vol: NA"
        )
        lines.append("CPI Metrics (H1):")
        lines.append(
            f"  H1_MaxPersistence: {c.h1_max_persist:.6f}"
            if np.isfinite(c.h1_max_persist)
            else "  H1_MaxPersistence: NA"
        )
        lines.append(
            f"  H1_CountAbove_Thr: {c.h1_count_above_thr:.0f}"
            if np.isfinite(c.h1_count_above_thr)
            else "  H1_CountAbove_Thr: NA"
        )
        lines.append(
            f"  H1_Entropy: {c.h1_entropy:.6f}"
            if np.isfinite(c.h1_entropy)
            else "  H1_Entropy: NA"
        )
        lines.append("Assessment:")
        lines.append(f"  H1_label: {c.h1_label}")

        if c.cycle_note:
            safe_note = str(c.cycle_note).replace('"', "'")
            lines.append(f'  Note: "{safe_note}"')

        if c.provenance:
            lines.append("Provenance:")
            for k, v in c.provenance.items():
                safe_v = str(v).replace('"', "'")
                lines.append(f'  {k}: "{safe_v}"')

        if c.notes:
            lines.append("Warnings:")
            for n in c.notes:
                safe_n = str(n).replace('"', "'")
                lines.append(f"  - {safe_n}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_tda_metrics_df(
    contexts: Sequence[TickerTDAContext],
    *,
    global_asof: pd.Timestamp,
) -> pd.DataFrame:
    if _COMPAT_TDA is not None and hasattr(_COMPAT_TDA, "build_tda_metrics_df"):
        try:
            df_out = _COMPAT_TDA.build_tda_metrics_df(contexts, global_asof=global_asof)  # type: ignore[attr-defined]
            return pd.DataFrame(df_out)
        except Exception:
            pass

    ga = pd.Timestamp(global_asof).strftime("%Y-%m-%d")
    rows: List[Dict[str, Any]] = []
    for c in contexts:
        rows.append(
            {
                "Global_AsOf": ga,
                "Ticker": c.ticker,
                "Ticker_AsOf": pd.Timestamp(c.asof).strftime("%Y-%m-%d")
                if pd.notna(c.asof)
                else "NA",
                "State": _state_to_str(getattr(c, "state", "")),
                "window_len": int(c.window_len),
                "embed_m": int(c.embed_m),
                "embed_tau": int(c.embed_tau),
                "persist_thr": float(c.persist_thr),
                # CPI-required columns
                "H1_MaxPersistence": float(c.h1_max_persist)
                if np.isfinite(c.h1_max_persist)
                else np.nan,
                "H1_CountAbove_Thr": float(c.h1_count_above_thr)
                if np.isfinite(c.h1_count_above_thr)
                else np.nan,
                "H1_Entropy": float(c.h1_entropy)
                if np.isfinite(c.h1_entropy)
                else np.nan,
                # diagnostics
                "n_obs_returns": int(c.n_obs),
                "n_embed_points": int(c.n_embed),
                "ret_vol": float(c.ret_vol) if np.isfinite(c.ret_vol) else np.nan,
                # legacy columns retained
                "H0_max_persist": float(c.h0_max_persist)
                if np.isfinite(c.h0_max_persist)
                else np.nan,
                "H1_max_persist": float(c.h1_max_persist)
                if np.isfinite(c.h1_max_persist)
                else np.nan,
                "H1_sum_persist": float(c.h1_sum_persist)
                if np.isfinite(c.h1_sum_persist)
                else np.nan,
                "H1_entropy_proxy": float(c.h1_entropy_proxy)
                if np.isfinite(c.h1_entropy_proxy)
                else np.nan,
                "H1_label": str(c.h1_label),
                "CycleNote": str(c.cycle_note),
                "Notes": " | ".join([str(x) for x in c.notes]) if c.notes else "",
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "DEFAULT_WINDOW_LEN",
    "DEFAULT_EMBED_M",
    "DEFAULT_EMBED_TAU",
    "DEFAULT_PERSIST_THR",
    "DEFAULT_LASTN",
    "TDAState",
    "TickerTDAContext",
    "compute_tda_for_ticker",
    "compute_tda_context",
    "build_tda_context_markdown",
    "build_tda_metrics_df",
]
