# ------------------------
# scripts\app3G.py
# ------------------------
from __future__ import annotations

import os
import sys
import logging
import warnings
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, cast

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
from scipy.signal import find_peaks
from statsmodels.stats.diagnostic import het_arch
from tabulate import tabulate


# ----------------------------
# Early path bootstrap (before importing legacy modules)
# ----------------------------

def _bootstrap_sys_path() -> Path:
    """
    Ensure imports work for:
      - src.* (package layer)
      - legacy modules in compat/ (Constants.py, Models.py, GUI.py, etc.)
    """
    this_file = Path(__file__).resolve()
    scripts_dir = this_file.parent
    app_root = scripts_dir.parent  # FIN root (../)

    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    compat_dir = app_root / "compat"
    if compat_dir.exists() and str(compat_dir) not in sys.path:
        sys.path.insert(0, str(compat_dir))

    return app_root


def _is_help_invocation(argv: list[str]) -> bool:
    """
    Return True if invoked only for help/usage.

    Phase-1 objective: avoid heavy side-effects (GPU init, worker setup,
    exo config load, etc.) when help is requested.
    """
    return any(a in ("-h", "--help") for a in argv)


APP_ROOT = _bootstrap_sys_path()


# ----------------------------
# FIN path layer
# ----------------------------

try:
    from src.config import paths
except Exception as e:
    raise RuntimeError(
        "Failed to import FIN path layer: from src.config import paths. "
        "Ensure src/config/paths.py exists and src/ is a package."
    ) from e


# ----------------------------
# Logging (must be set up before other imports log)
# ----------------------------

def _configure_logging() -> logging.Logger:
    paths.ensure_directories()  # explicit side-effect allowed in entrypoint

    log_format = "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    log_file = paths.LOGS_DIR / "Logs.log"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(str(log_file), mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger(__name__)
    logger.info("FIN app3G bootstrap complete. APP_ROOT=%s", paths.APP_ROOT)
    logger.info("Logs: %s", log_file)
    return logger


log = _configure_logging()

# Reduce TensorFlow noise if present (done before importing compat/tf)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
warnings.filterwarnings("ignore")


# ----------------------------
# Lazy legacy module handles (only import when needed)
# ----------------------------

C = None          # Constants
compat = None     # compat package bridge
Models = None     # Models facade
GUI = None        # GUI module
Pivots = None     # pivots module
ExoConfig = None  # exogenous config module
EXO_CONFIG = None # loaded config


def _import_legacy_modules() -> None:
    """
    Import legacy modules only when actually running the application.
    This keeps `--help` fast and side-effect light.
    """
    global C, compat, Models, GUI, Pivots, ExoConfig

    if C is not None:
        return

    # These come from compat/ on sys.path; keep names as-is to avoid touching legacy code.
    import Constants as _C  # type: ignore
    import compat as _compat  # type: ignore
    import Models as _Models  # type: ignore
    import GUI as _GUI  # type: ignore
    import Pivots as _Pivots  # type: ignore
    import ExoConfig as _ExoConfig  # type: ignore

    C = _C
    compat = _compat
    Models = _Models
    GUI = _GUI
    Pivots = _Pivots
    ExoConfig = _ExoConfig


def _bridge_constants() -> None:
    """
    Keep legacy modules functional by overriding path constants at runtime.
    """
    assert C is not None, "Constants module not imported"
    C.APP_ROOT_DIR = str(paths.WORKERS_DIR)
    C.DATA_FOLDER = str(paths.DATA_RAW_DIR)
    C.GRAPHS_FOLDER = str(paths.GRAPHS_DIR)

    log.info("Constants bridge applied:")
    log.info("  C.APP_ROOT_DIR   = %s (workers)", C.APP_ROOT_DIR)
    log.info("  C.DATA_FOLDER    = %s", C.DATA_FOLDER)
    log.info("  C.GRAPHS_FOLDER  = %s", C.GRAPHS_FOLDER)


def _load_exo_config_once() -> None:
    global EXO_CONFIG
    assert ExoConfig is not None, "ExoConfig not imported"
    assert C is not None, "Constants not imported"

    if EXO_CONFIG is not None:
        return

    EXO_CONFIG = ExoConfig.load_exo_config(
        csv_path=str(paths.EXO_CONFIG_PATH),
        forecast_horizon=int(C.FH),
    )


# ----------------------------
# GPU setup (TensorFlow optional)
# ----------------------------

def setup_gpu() -> None:
    """Initializes GPU for TensorFlow if available."""
    assert compat is not None, "compat not imported"
    if getattr(compat, "HAS_TENSORFLOW", False):
        tf_mod = getattr(compat, "tf", None)
        if tf_mod is None:
            log.warning("TensorFlow flag true but compat.tf is None. Proceeding on CPU.")
            return

        gpus = tf_mod.config.list_physical_devices("GPU")
        if gpus:
            try:
                for gpu in gpus:
                    tf_mod.config.experimental.set_memory_growth(gpu, True)
                log.info("TensorFlow: GPU available and configured: %s", gpus)
            except RuntimeError as e:
                log.warning("TensorFlow: GPU memory growth setup failed: %s. Proceeding on CPU.", e)
        else:
            log.info("TensorFlow: GPU not available. Using CPU.")


# ----------------------------
# Plot helpers (Pylance-safe)
# ----------------------------

def _as_datetime_index(idx: pd.Index) -> pd.DatetimeIndex:
    """
    Defensive conversion for Matplotlib date handling and type narrowing.
    """
    if isinstance(idx, pd.DatetimeIndex):
        out = idx
    else:
        out = pd.to_datetime(idx, errors="coerce")
        out = cast(pd.DatetimeIndex, out)

    if out.hasnans:
        out = out[~out.isna()]
    return cast(pd.DatetimeIndex, out)


def _safe_timestamp(obj: Any) -> pd.Timestamp:
    """
    Convert timestamp-like objects to pandas Timestamp with a safe fallback.

    Rationale:
    - Pylance may treat DatetimeIndex.__getitem__ as returning Timestamp | DatetimeIndex.
    - Using a wrapper returning Any-narrowed Timestamp avoids reportArgumentType false positives.
    """
    try:
        return pd.Timestamp(cast(Any, obj))
    except Exception:
        return pd.Timestamp(str(obj))


def _date2num_index(idx: pd.Index) -> np.ndarray:
    """
    Convert pandas index to Matplotlib float date numbers (days since epoch).
    """
    dti = _as_datetime_index(idx)
    py_dt = dti.to_pydatetime()
    return np.asarray(mdates.date2num(py_dt), dtype=float)


def _date2num_one(ts_like: Any) -> float:
    """
    Convert a single timestamp-like value to Matplotlib float date number.
    """
    ts = _safe_timestamp(ts_like)
    return float(mdates.date2num(ts.to_pydatetime()))


def _to_float_array(obj: Any) -> np.ndarray:
    """
    Convert a Series/array-like/scalar into float ndarray.
    Keeps NaNs for masking.
    """
    if isinstance(obj, pd.Series):
        s = cast(pd.Series, obj)
        numeric = pd.to_numeric(s, errors="coerce")
        if isinstance(numeric, pd.Series):
            return numeric.to_numpy(dtype=float)
        return np.asarray(numeric, dtype=float)

    if isinstance(obj, (np.ndarray, list, tuple)):
        return np.asarray(obj, dtype=float)

    try:
        return np.asarray([float(obj)], dtype=float)
    except Exception:
        return np.asarray([np.nan], dtype=float)


# ----------------------------
# Plotting
# ----------------------------

def create_plot(plot_args: Dict[str, Any]) -> None:
    """Generates and saves the final analysis plot with all features and styling."""
    fig = None
    try:
        data: pd.DataFrame = plot_args["data"]
        ticker: str = plot_args["ticker"]
        period: str = plot_args["period"]
        model_results: Dict[str, Optional[pd.DataFrame]] = plot_args["model_results"]
        garch_vol_forecast: Optional[pd.DataFrame] = plot_args["garch_vol_forecast"]
        show_peaks: bool = plot_args["show_peaks"]
        show_regimes: bool = plot_args["show_regimes"]
        pivot_data = plot_args["pivot_data"]

        assert C is not None, "Constants not imported"
        assert compat is not None, "compat not imported"

        model_styles = {
            "PyCaret": {"color": "#333333", "marker": "x", "linestyle": "--", "label": "PyCaret"},
            "ARIMAX":  {"color": "#8A2BE2", "marker": "s", "linestyle": "--", "label": "ARIMAX", "ms": 5, "fill_color": "#E6E6FA"},
            "PCE":     {"color": "#228B22", "marker": "o", "linestyle": "--", "label": "PCE-NARX", "ms": 5, "fill_color": "#E0FFE0"},
            "LSTM":    {"color": "#FF8C00", "marker": "o", "linestyle": ":",  "label": "LSTM", "ms": 5, "fill_color": "#FFF5E1"},
            "GARCH":   {"color": "#DC143C", "marker": "^", "linestyle": ":",  "label": "GARCH", "ms": 5},
            "VAR":     {"color": "#008B8B", "marker": "D", "linestyle": "-.", "label": "VAR", "ms": 4},
            "ETS":     {"color": "#00BFFF", "marker": "+", "linestyle": ":",  "label": "ETS", "mew": 2},
            "RW":      {"color": "gray",    "marker": None, "linestyle": "-.", "label": "RW"},
        }

        indicator_styles = {
            "RSI (14)": {"color": "green", "linestyle": "-", "linewidth": 1.5},
            "Stochastic %K": {"color": "purple", "linestyle": "--", "linewidth": 1.5},
            "Williams %R": {"color": "red", "linestyle": ":", "linewidth": 1.5},
            "Ultimate Oscillator": {"color": "blue", "linestyle": "-.", "linewidth": 1.0},
            "STOCH_%D": {"color": "gray", "linestyle": ":", "linewidth": 1.0},
        }
        default_indicator_style = {"linestyle": ":", "alpha": 0.7}

        # Normalize index to DatetimeIndex to avoid mixed hashable labels
        data = data.copy()
        data.index = _as_datetime_index(data.index)
        data = data.sort_index()

        plt.close("all")
        fig = plt.figure(figsize=(16, 12))
        gs = GridSpec(3, 1, height_ratios=[3, 1, 1.5], hspace=0.05)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[1, 0], sharex=ax1)
        ax3 = fig.add_subplot(gs[2, 0], sharex=ax1)

        ax1.set_title(f"{ticker} Analysis & {C.FH}-Day Forecast ({period} History)")
        ax1.set_ylabel("Stock Price / Predictions", color="tab:blue")
        ax1.tick_params(axis="y", labelcolor="tab:blue")
        ax1.grid(True, which="both", linestyle="--", linewidth=0.5)
        plt.setp(ax1.get_xticklabels(), visible=False)

        offset_map = {"1m": pd.DateOffset(months=1), "3m": pd.DateOffset(months=3)}
        last_dt = _safe_timestamp(_as_datetime_index(data.index)[-1])
        start_date = _safe_timestamp(last_dt) - offset_map.get(period, pd.DateOffset(months=3))
        plot_data = data.loc[start_date:].copy()

        if "Close" not in plot_data.columns or plot_data.empty:
            log.warning("Plot: missing Close series after filtering.")
            return

        close_series_raw = cast(pd.Series, plot_data["Close"])
        close_numeric = pd.to_numeric(close_series_raw, errors="coerce")
        close_series = cast(pd.Series, close_numeric).dropna()

        if close_series.empty:
            log.warning("Plot: Close series became empty after numeric coercion/dropna.")
            return

        # Re-align plot_data to Close series index after dropna
        plot_data = plot_data.reindex(close_series.index)

        ax1.plot(close_series.index, close_series, label="Close Price", lw=2.5, zorder=10)

        model_plot_order = ["PyCaret", "ARIMAX", "PCE", "LSTM", "GARCH", "VAR", "ETS", "RW"]
        forecast_dates: Optional[pd.Index] = None

        for name in model_plot_order:
            preds = model_results.get(name)
            if preds is None or preds.empty:
                continue

            preds = preds.copy()
            preds.index = _as_datetime_index(preds.index)
            preds = preds.sort_index()

            if forecast_dates is None:
                forecast_dates = preds.index

            pred_col = f"{name}_Pred"
            lower_col = f"{name}_Lower"
            upper_col = f"{name}_Upper"
            if pred_col not in preds.columns:
                continue

            style = model_styles.get(name, {})
            plot_style = {k: v for k, v in style.items() if k != "fill_color"}

            ax1.plot(preds.index, preds[pred_col], **plot_style, zorder=11)

            fill_color = style.get("fill_color", style.get("color", "gray"))

            if lower_col in preds.columns and upper_col in preds.columns:
                lower_arr = _to_float_array(preds[lower_col])
                upper_arr = _to_float_array(preds[upper_col])
                x_fill = _date2num_index(preds.index)

                ok = np.isfinite(lower_arr) & np.isfinite(upper_arr) & np.isfinite(x_fill)
                if np.any(ok):
                    cast(Any, ax1).fill_between(
                        x_fill[ok],
                        lower_arr[ok],
                        upper_arr[ok],
                        color=fill_color,
                        alpha=0.4,
                        zorder=1,
                        edgecolor=style.get("color", "gray"),
                        linewidth=0.5,
                    )

        if show_peaks:
            close_vals = _to_float_array(close_series)
            peaks, _ = find_peaks(
                close_vals,
                prominence=float(C.PEAK_PROM),
                distance=int(C.PEAK_DIST),
                width=int(C.PEAK_WIDTH),
            )
            troughs, _ = find_peaks(
                -close_vals,
                prominence=float(C.PEAK_PROM),
                distance=int(C.PEAK_DIST),
                width=int(C.PEAK_WIDTH),
            )

            ax1.plot(close_series.index[peaks], close_series.iloc[peaks], "v", color="red", ms=8, label="Peaks", zorder=12)
            ax1.plot(close_series.index[troughs], close_series.iloc[troughs], "^", color="green", ms=8, label="Troughs", zorder=12)

        if pivot_data and "Classic" in pivot_data and forecast_dates is not None and len(forecast_dates) > 1:
            pivot_levels = pivot_data["Classic"]

            fd = _as_datetime_index(forecast_dates)
            line_start_date = _safe_timestamp(plot_data.index[0]) + pd.DateOffset(days=2)
            line_end_date = _safe_timestamp(fd[1])
            label_date = _safe_timestamp(plot_data.index[0]) + pd.DateOffset(days=1)

            pivot_colors = {
                "R3": "darkred",
                "R2": "red",
                "R1": "lightcoral",
                "Pivot": "black",
                "S1": "palegreen",
                "S2": "green",
                "S3": "darkgreen",
            }

            for nm, value in pivot_levels.items():
                if pd.notna(value):
                    ax1.plot(
                        [line_start_date, line_end_date],
                        [value, value],
                        color=pivot_colors.get(nm, "gray"),
                        linestyle="--",
                        linewidth=1.2,
                        zorder=5,
                    )
                    ax1.text(
                        _date2num_one(label_date),
                        float(value),
                        f" {nm}",
                        color=pivot_colors.get(nm, "gray"),
                        va="center",
                        ha="left",
                        fontsize=9,
                        bbox=dict(facecolor="white", alpha=0.5, edgecolor="none", boxstyle="round,pad=0.1"),
                        zorder=12,
                    )

        if show_regimes and getattr(compat, "HAS_RUPTURES", False):
            rpt = getattr(compat, "rpt", None)
            if rpt is not None:
                points = np.array(close_series.values, dtype=float)
                algo = rpt.Pelt(model=str(C.REGIME_METHOD)).fit(points)
                result = algo.predict(pen=float(C.PELT_PENALTY))
                print(f"\nRegime change points (end indices): {result}")

                bkps = [0] + list(result)
                for i in range(len(bkps) - 1):
                    start_idx, end_idx = int(bkps[i]), int(bkps[i + 1])
                    if start_idx < len(close_series) and end_idx <= len(close_series):
                        start_date_reg = _safe_timestamp(_as_datetime_index(close_series.index)[start_idx])
                        end_date_reg = _safe_timestamp(_as_datetime_index(close_series.index)[end_idx - 1])

                        cast(Any, ax1).axvspan(
                            _date2num_one(start_date_reg),
                            _date2num_one(end_date_reg),
                            alpha=0.2,
                            color="orange" if i % 2 == 0 else "gray",
                            label="_nolegend_",
                        )

                        label_x_pos = start_date_reg + (end_date_reg - start_date_reg) / 2
                        y_min, y_max = ax1.get_ylim()
                        label_y_pos = y_min + (y_max - y_min) * 0.03

                        ax1.text(
                            _date2num_one(label_x_pos),
                            float(label_y_pos),
                            f"Region {i + 1}",
                            ha="center",
                            va="bottom",
                            fontsize=9,
                            color="black",
                            bbox=dict(facecolor="white", alpha=0.6, edgecolor="none", boxstyle="round,pad=0.2"),
                            zorder=12,
                        )

        # Date axis formatting
        locator = mdates.AutoDateLocator()
        ax3.xaxis.set_major_locator(locator)
        ax3.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

        ax2.set_ylabel("GARCH Volatility", color="tab:red")
        ax2.grid(True, which="both", linestyle="--", linewidth=0.5)
        plt.setp(ax2.get_xticklabels(), visible=False)

        if garch_vol_forecast is not None and not garch_vol_forecast.empty:
            garch_vol_forecast = garch_vol_forecast.copy()
            garch_vol_forecast.index = _as_datetime_index(garch_vol_forecast.index)
            if "Volatility_Forecast" in garch_vol_forecast.columns:
                ax2.plot(
                    garch_vol_forecast.index,
                    garch_vol_forecast["Volatility_Forecast"],
                    color="tab:red",
                    linestyle="--",
                    marker="o",
                    label="GARCH Vol Forecast",
                )

        if "GARCH_Hist_Vol" in plot_data.columns:
            ax2.plot(plot_data.index, plot_data["GARCH_Hist_Vol"], color="gray", alpha=0.7, label="Historical Vol^2")

        ax3.set_ylabel("Indicator Oscillators")
        ax3.grid(True, which="both", linestyle="--", linewidth=0.5)
        ax3.set_ylim(-5, 105)
        ax3.axhline(80, color="red", linestyle="--", linewidth=0.8, alpha=0.5)
        ax3.axhline(20, color="green", linestyle="--", linewidth=0.8, alpha=0.5)
        ax3.axhline(50, color="gray", linestyle=":", linewidth=0.8, alpha=0.5)

        for indicator in C.INDICATORS_0_100:
            if indicator in plot_data.columns:
                style = indicator_styles.get(indicator, default_indicator_style)
                ax3.plot(plot_data.index, plot_data[indicator], label=indicator, **style)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        lines3, labels3 = ax3.get_legend_handles_labels()

        fig.legend(
            lines1 + lines2 + lines3,
            labels1 + labels2 + labels3,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.01),
            ncol=8,
        )
        fig.tight_layout(rect=(0, 0.05, 1, 0.97))

        graph_filename = Path(C.GRAPHS_FOLDER) / f"{ticker}_{period}_plot.png"
        plt.savefig(str(graph_filename), bbox_inches="tight", dpi=150)
        print(f"Plot saved to {graph_filename}")

    finally:
        if fig is not None:
            plt.close(fig)


# ----------------------------
# Markdown formatting helpers
# ----------------------------

def format_indicator_table(ticker: str, date: Any, latest_indicators: pd.Series, pivot_data) -> str:
    assert C is not None, "Constants not imported"
    if latest_indicators is None or latest_indicators.empty:
        return "Could not generate indicator table."

    date_ts = _safe_timestamp(date)
    header = f"#### Indicators for {ticker} ({date_ts.strftime('%Y-%m-%d')}):"

    indicator_map = {
        "Current Value": "Close",
        "Classic Pivot Point": "Classic Pivot",
        "50-day MA": "MA50",
        "200-day MA": "MA200",
        "RSI (14)": "RSI (14)",
        "Stochastic %K": "Stochastic %K",
        "ATR (14)": "ATR (14)",
        "ADX (14)": "ADX (14)",
        "CCI (14)": "CCI (14)",
        "Williams %R": "Williams %R",
        "Ultimate Oscillator": "Ultimate Oscillator",
        "ROC (10)": "ROC (10)",
        "BullBear Power": "BullBear Power",
    }

    table = [
        header,
        "| Indicator             | Value        |",
        "|:----------------------|-------------:|",
    ]

    for display_name, series_name in indicator_map.items():
        value = None
        if series_name == "Classic Pivot":
            if pivot_data and "Classic" in pivot_data and "Pivot" in pivot_data["Classic"]:
                value = pivot_data["Classic"]["Pivot"]
        elif series_name in latest_indicators:
            value = latest_indicators[series_name]

        value_str = f"{value:,.4f}" if pd.notna(value) else "N/A"
        table.append(f"| {display_name:<21} | {value_str:>12} |")

    return "\n".join(table)


def format_forecast_table(ticker: str, model_results: Dict[str, Optional[pd.DataFrame]]) -> str:
    assert C is not None, "Constants not imported"
    header = f"#### {ticker} Forecasting results (Day {C.FH}):"
    model_order = ["PyCaret", "ARIMAX", "PCE", "LSTM", "GARCH", "VAR", "RW", "ETS"]
    table = [
        header,
        "| Model   | Lower CI | Forecast | Upper CI |",
        "|:--------|:--------:|:--------:|:--------:|",
    ]

    for model_name in model_order:
        preds_df = model_results.get(model_name)
        pred_col = f"{model_name}_Pred"
        lower_col = f"{model_name}_Lower"
        upper_col = f"{model_name}_Upper"

        if preds_df is None or preds_df.empty or len(preds_df) < int(C.FH) or pred_col not in preds_df:
            pred_str, lower_str, upper_str = "-", "-", "-"
        else:
            final_day = preds_df.iloc[-1]
            pred_str = f"{float(final_day[pred_col]):.4f}"
            lower_str = f"{float(final_day[lower_col]):.4f}" if lower_col in final_day and pd.notna(final_day[lower_col]) else "-"
            upper_str = f"{float(final_day[upper_col]):.4f}" if upper_col in final_day and pd.notna(final_day[upper_col]) else "-"

        table.append(f"| {model_name:<7} | {lower_str:>8} | {pred_str:>8} | {upper_str:>8} |")

    return "\n".join(table)


def format_garch_vol_table(ticker: str, garch_vol_forecast: Optional[pd.DataFrame]) -> str:
    if garch_vol_forecast is None or garch_vol_forecast.empty:
        return ""
    header = f"#### {ticker} GARCH Volatility Forecast (Variance):"
    table = [
        header,
        "| Date       | Forecast |",
        "|:-----------|:---------|",
    ]
    for date, row in garch_vol_forecast.iterrows():
        date_ts = _safe_timestamp(date)
        table.append(f"| {date_ts.strftime('%Y-%m-%d')} | {float(row['Volatility_Forecast']):.4f}   |")
    return "\n".join(table)


def format_garch_summary_markdown(ticker: str, garch_results) -> str:
    if garch_results is None:
        return ""
    try:
        summary_tables = garch_results.summary().tables
        if len(summary_tables) < 3:
            return garch_results.summary().as_text()

        results_data = summary_tables[0].data
        table1_data = [results_data[i][:2] for i in range(len(results_data))] + [results_data[i][2:] for i in range(len(results_data))]
        header1 = "**AR-X - GARCH Model Results**"
        table1_md = tabulate(table1_data, headers=["**Parameter**", "**Value**"], tablefmt="pipe")

        header2 = "**Mean Model**"
        table2_headers_raw = summary_tables[1].data[0]
        table2_headers = [h.replace("P>|t|", "P>abs(t)") for h in table2_headers_raw]
        table2_data = summary_tables[1].data[1:]
        table2_md = tabulate(table2_data, headers=table2_headers, tablefmt="pipe")

        header3 = "**Volatility Model**"
        table3_headers_raw = summary_tables[2].data[0]
        table3_headers = [h.replace("P>|t|", "P>abs(t)") for h in table3_headers_raw]
        table3_data = summary_tables[2].data[1:]
        table3_md = tabulate(table3_data, headers=table3_headers, tablefmt="pipe")

        footer = "**Covariance estimator: robust**"
        return f"{header1}\n{table1_md}\n\n{header2}\n{table2_md}\n\n{header3}\n{table3_md}\n\n{footer}"
    except Exception as e:
        log.warning("Could not format GARCH summary to Markdown; falling back to text. Error: %s", e)
        return garch_results.summary().as_text()


# ----------------------------
# Orchestrated pipeline
# ----------------------------

def analysis_pipeline(
    ticker: str,
    period: str,
    show_peaks: bool,
    show_regimes: bool,
    progress_callback,
    exo_config=None,
) -> Tuple[bool, float]:
    """
    Complete, orchestrated analysis pipeline.
    """
    try:
        assert Models is not None, "Models not imported"
        assert Pivots is not None, "Pivots not imported"
        assert C is not None, "Constants not imported"
        assert compat is not None, "compat not imported"

        if exo_config is None:
            exo_config = EXO_CONFIG

        progress_callback(5, "Calculating technical indicators...")

        enriched_data = Models.run_external_ti_calculator(ticker)
        if enriched_data is None:
            return False, 0.0

        if getattr(compat, "HAS_ARCH", False):
            enriched_data["GARCH_Hist_Vol"] = (100 * enriched_data["Close"].pct_change()).pow(2)

        atr_change_std = float(enriched_data["ATR (14)"].diff().std()) if "ATR (14)" in enriched_data.columns else 0.0

        latest_indicators = enriched_data.iloc[-1]
        pivot_data = Pivots.calculate_latest_pivot_points(enriched_data)

        print("\n" + format_indicator_table(ticker, latest_indicators.name, latest_indicators, pivot_data))
        if pivot_data:
            print("\n" + Pivots.format_pivot_table(pivot_data, ticker, latest_indicators.name))
            print()

        progress_callback(20, "Running forecast models...")

        arimax_preds, arimax_order, arimax_residuals = Models.predict_arima(
            enriched_data,
            ticker=ticker,
            exo_config=exo_config,
        )

        if arimax_residuals is not None and getattr(compat, "HAS_ARCH", False):
            p_value = float(het_arch(arimax_residuals, nlags=10)[1])
            test_result = "Significant (GARCH is appropriate)" if p_value < 0.05 else "Not Significant"
            print(f"ARIMAX Residual ARCH Test (p-value): {p_value:.4f} -> {test_result}\n")

        if getattr(compat, "HAS_ARCH", False):
            garch_price_forecast, garch_vol_forecast, garch_results = Models.predict_arch_model(
                enriched_data,
                ticker=ticker,
                exo_config=exo_config,
            )
        else:
            garch_price_forecast, garch_vol_forecast, garch_results = None, None, None

        model_results: Dict[str, Optional[pd.DataFrame]] = {
            "PyCaret": Models.run_external_pycaret(ticker),
            "ARIMAX": arimax_preds,
            "PCE": Models.predict_pce_narx(enriched_data, ticker=ticker, exo_config=exo_config),
            "LSTM": Models.predict_lstm(enriched_data, ticker=ticker, exo_config=exo_config) if getattr(compat, "HAS_TENSORFLOW", False) else None,
            "GARCH": garch_price_forecast,
            "ETS": Models.predict_exp_smoothing(enriched_data),
            "RW": Models.predict_random_walk(enriched_data),
            "VAR": Models.predict_var(enriched_data) if getattr(compat, "HAS_STATSMODELS", False) else None,
        }

        print("\n" + format_forecast_table(ticker, model_results))
        if arimax_order:
            print(f"\n* ARIMAX Model Selected: p,d,q = {arimax_order} with configured exogenous regressors.")

        if garch_results:
            print("\n#### GARCH Model Summary:\n")
            print(format_garch_summary_markdown(ticker, garch_results))
            print("\n" + format_garch_vol_table(ticker, garch_vol_forecast))

        progress_callback(90, "Creating plot...")

        plot_args = {
            "data": enriched_data,
            "ticker": ticker,
            "period": period,
            "model_results": model_results,
            "garch_vol_forecast": garch_vol_forecast,
            "show_peaks": show_peaks,
            "show_regimes": show_regimes,
            "pivot_data": pivot_data,
        }
        create_plot(plot_args)

        progress_callback(100, "Analysis Complete.")
        return True, atr_change_std

    except Exception as e:
        log.error("An error occurred during the analysis pipeline for %s: %s", ticker, e, exc_info=True)
        messagebox.showerror("Analysis Failed", f"An unexpected error occurred: {e}")
        return False, 0.0


# ----------------------------
# Application Entry Point
# ----------------------------

def _startup_sanity_checks() -> None:
    """
    Validate required FIN directories and inputs exist; create directories via ensure_directories().
    """
    paths.ensure_directories()

    if not paths.DATA_RAW_DIR.exists():
        messagebox.showerror(
            "Startup Error",
            f"Raw data folder not found:\n{paths.DATA_RAW_DIR}\n"
            "Please ensure data/raw exists and contains *_data.csv files."
        )
        raise SystemExit(1)

    if not paths.EXO_CONFIG_PATH.exists():
        log.warning("Exogenous config not found at %s. Exogenous scenarios will be disabled.", paths.EXO_CONFIG_PATH)

    if not paths.GRAPHS_DIR.exists():
        messagebox.showerror("Startup Error", f"Graphs folder not found and could not be created:\n{paths.GRAPHS_DIR}")
        raise SystemExit(1)


def _print_help_stub() -> None:
    """
    Minimal help output without importing legacy modules or doing heavy init.
    """
    exe = Path(sys.executable).name
    print("FIN app3G (GUI entrypoint)")
    print("")
    print("Usage:")
    print(f"  {exe} scripts\\app3G.py            # start GUI")
    print(f"  {exe} scripts\\app3G.py --help     # show this help")
    print("")
    print("Notes:")
    print("  - This is a GUI entrypoint; forecasting runs via the GUI.")
    print("  - Workers live under scripts\\workers and are invoked by compat Models.")
    print("")


if __name__ == "__main__":
    # Fast path for help/usage: do not import legacy stack, do not init GPU, do not load exo config.
    if _is_help_invocation(sys.argv[1:]):
        _print_help_stub()
        raise SystemExit(0)

    # Full run path
    _startup_sanity_checks()

    _import_legacy_modules()
    _bridge_constants()
    _load_exo_config_once()

    setup_gpu()

    root = tk.Tk()
    app = GUI.StockAnalysisApp(root, analysis_callback=analysis_pipeline)  # type: ignore[attr-defined]
    root.mainloop()
