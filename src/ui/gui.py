# ------------------------
# src/ui/gui.py
# ------------------------

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Tuple, cast

import tkinter as tk
from tkinter import messagebox, ttk

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Bootstrap: ensure FIN root is importable when running from arbitrary CWD
# ----------------------------------------------------------------------


def _bootstrap_sys_path() -> Path:
    """
    Expected location:
        FIN/src/ui/gui.py

    Therefore project root is:
        <this_file>/../../
    """
    here = Path(__file__).resolve()
    app_root = here.parents[2]
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    compat_dir = app_root / "compat"
    if compat_dir.exists() and str(compat_dir) not in sys.path:
        sys.path.insert(0, str(compat_dir))
    return app_root


APP_ROOT = _bootstrap_sys_path()


# ----------------------------------------------------------------------
# Optional: legacy Constants (preferred if present)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class _Defaults:
    APP_VERSION: str = "0.0"
    TICKERS: Tuple[str, ...] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")
    SHOW_PEAKS_TROUGHS: bool = True
    SHOW_REGIMES: bool = False
    HISTORY_PERIODS: Tuple[str, ...] = ("1m", "3m")


def _load_constants_or_defaults() -> _Defaults:
    """
    If Constants.py exists (legacy), use it. Otherwise run with safe defaults.
    """
    try:
        import Constants as C  # type: ignore

        app_version = str(getattr(C, "APP_VERSION", _Defaults.APP_VERSION))
        tickers_any = getattr(C, "TICKERS", _Defaults.TICKERS)
        show_peaks = bool(
            getattr(C, "SHOW_PEAKS_TROUGHS", _Defaults.SHOW_PEAKS_TROUGHS)
        )
        show_regimes = bool(getattr(C, "SHOW_REGIMES", _Defaults.SHOW_REGIMES))

        # Legacy GUI had fixed ['1m','3m']; allow override if added later.
        periods_any = getattr(C, "HISTORY_PERIODS", _Defaults.HISTORY_PERIODS)

        # Ensure tuples of str for UI controls (static typing + runtime safety)
        tickers = (
            tuple(str(x) for x in tickers_any) if tickers_any else _Defaults.TICKERS
        )
        periods = (
            tuple(str(x) for x in periods_any)
            if periods_any
            else _Defaults.HISTORY_PERIODS
        )

        return _Defaults(
            APP_VERSION=app_version,
            TICKERS=cast(Tuple[str, ...], tickers),
            SHOW_PEAKS_TROUGHS=show_peaks,
            SHOW_REGIMES=show_regimes,
            HISTORY_PERIODS=cast(Tuple[str, ...], periods),
        )
    except Exception:
        return _Defaults()


# src.utils.compat for optional dependency gating
try:
    from src.utils import compat as fin_compat  # type: ignore
except Exception:  # pragma: no cover
    fin_compat = None


# ----------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------


class StockAnalysisApp:
    """

    ALL_TICKERS_LABEL = "ALL_TICKERS"
    Tkinter GUI for FIN analysis & forecasting.

    analysis_callback contract:
      analysis_callback(
          ticker: str,
          period: str,
          show_peaks: bool,
          show_regimes: bool,
          progress_callback: Callable[[int, str], None],
      ) -> Tuple[bool, float]

    Return:
      (success, hint_value)
        - success: True iff analysis completed and artifact(s) were produced.
        - hint_value: typical ΔATR or similar (float), or <= 0 if unavailable.
    """

    def __init__(
        self, root: tk.Tk, analysis_callback: Callable[..., Tuple[bool, float]]
    ):
        self.root = root
        self.analysis_callback = analysis_callback

        self.C = _load_constants_or_defaults()

        title = f"FIN — Stock Analysis & Forecast v{self.C.APP_VERSION}"
        self.root.title(title)
        self.root.geometry("480x520")

        control_frame = ttk.Frame(root, padding="15")
        control_frame.pack(expand=True, fill=tk.BOTH)
        control_frame.columnconfigure(1, weight=1)

        # ---- Ticker selection
        ttk.Label(control_frame, text="Select Ticker:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )

        self.ticker_var = tk.StringVar(value=self.C.TICKERS[0])
        ticker_values = [self.ALL_TICKERS_LABEL] + list(self.C.TICKERS)
        self.ticker_menu = ttk.Combobox(
            control_frame,
            textvariable=self.ticker_var,
            values=ticker_values,
            state="readonly",
        )
        self.ticker_menu.grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=(5, 0))

        # ---- History period selection
        ttk.Label(control_frame, text="Select History Period:").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )

        self.period_var = tk.StringVar(value=self.C.HISTORY_PERIODS[0])
        self.period_menu = ttk.Combobox(
            control_frame,
            textvariable=self.period_var,
            values=list(self.C.HISTORY_PERIODS),
            state="readonly",
        )
        self.period_menu.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=(5, 0))

        # ---- Display options
        options_frame = ttk.LabelFrame(
            control_frame, text="Display Options", padding=10
        )
        options_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(10, 5))

        self.show_peaks_var = tk.BooleanVar(value=bool(self.C.SHOW_PEAKS_TROUGHS))
        ttk.Checkbutton(
            options_frame, text="Show Peaks/Troughs", variable=self.show_peaks_var
        ).pack(side=tk.LEFT, padx=5)

        self.show_regimes_var = tk.BooleanVar(value=bool(self.C.SHOW_REGIMES))
        self.regime_button = ttk.Checkbutton(
            options_frame, text="Show Regimes", variable=self.show_regimes_var
        )
        self.regime_button.pack(side=tk.LEFT, padx=5)

        # Capability gating: ruptures required
        has_ruptures = (
            bool(getattr(fin_compat, "HAS_RUPTURES", False)) if fin_compat else False
        )
        if not has_ruptures:
            self.regime_button.config(state=tk.DISABLED)
            self.show_regimes_var.set(False)

        # ---- Scenario info (CSV-driven; informational only)
        self.scenario_frame = ttk.LabelFrame(
            control_frame,
            text="Scenario Forecasting (configured via Exo_regressors.csv)",
            padding=10,
        )
        self.scenario_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=5)
        self.scenario_frame.columnconfigure(0, weight=1)

        self.style = ttk.Style(self.root)
        self.style.configure("Hint.TLabel", foreground="gray")

        self.delta_atr_var = tk.StringVar(
            value="Δ(ATR(14)): (Run analysis to calculate)"
        )
        self.delta_atr_label = ttk.Label(
            self.scenario_frame, textvariable=self.delta_atr_var, style="Hint.TLabel"
        )
        self.delta_atr_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=(2, 2))

        # ---- Progress + status
        self.progress_bar = ttk.Progressbar(
            control_frame, length=340, mode="determinate"
        )
        self.progress_bar.grid(row=4, column=0, columnspan=2, pady=10, sticky=tk.EW)

        self.status_label = ttk.Label(control_frame, text="Status: Ready")
        self.status_label.grid(row=5, column=0, columnspan=2, sticky=tk.EW)

        # ---- Action button
        self.analyze_button = ttk.Button(
            control_frame, text="Analyze & Forecast", command=self.on_analyze_threaded
        )
        self.analyze_button.grid(row=6, column=0, columnspan=2, pady=15, ipady=5)

    # ------------------------------------------------------------------
    # Threaded execution
    # ------------------------------------------------------------------

    def on_analyze_threaded(self) -> None:
        """Start analysis in a background thread (keeps UI responsive)."""
        self.analyze_button.config(state=tk.DISABLED)
        self.update_progress(0, "Starting...")
        self.delta_atr_var.set("Δ(ATR(14)): Calculating...")

        analysis_args = {
            "ticker": self.ticker_var.get(),
            "period": self.period_var.get(),
            "show_peaks": bool(self.show_peaks_var.get()),
            "show_regimes": bool(self.show_regimes_var.get()),
        }

        threading.Thread(
            target=self.analysis_thread_target,
            args=(analysis_args,),
            daemon=True,
        ).start()

    def analysis_thread_target(self, analysis_args: dict) -> None:
        """Worker thread: call pipeline and then marshal results back to UI thread."""
        ticker_sel = str(analysis_args.get("ticker", ""))
        period = str(analysis_args.get("period", ""))
        show_peaks = bool(analysis_args.get("show_peaks", False))
        show_regimes = bool(analysis_args.get("show_regimes", False))

        try:
            if ticker_sel == self.ALL_TICKERS_LABEL:
                tickers = list(self.C.TICKERS)
                log.info("GUI: Starting batch analysis for tickers=%s", tickers)

                successes = 0
                hint_values: list[float] = []
                for idx, ticker in enumerate(tickers, start=1):
                    self.update_progress_safe(
                        int(((idx - 1) / max(1, len(tickers))) * 100),
                        f"Batch {idx}/{len(tickers)} starting: {ticker}",
                    )
                    ok, hint = self.analysis_callback(
                        ticker=ticker,
                        period=period,
                        show_peaks=show_peaks,
                        show_regimes=show_regimes,
                        progress_callback=self.update_progress_safe,
                    )
                    if ok:
                        successes += 1
                    if hint and float(hint) > 0.0:
                        hint_values.append(float(hint))

                batch_ok = successes == len(tickers)
                avg_hint = (sum(hint_values) / len(hint_values)) if hint_values else 0.0
                result = (batch_ok, float(avg_hint))
                label = self.ALL_TICKERS_LABEL
            else:
                ticker = ticker_sel
                log.info("GUI: Starting analysis thread for %s ...", ticker)
                result = self.analysis_callback(
                    ticker=ticker,
                    period=period,
                    show_peaks=show_peaks,
                    show_regimes=show_regimes,
                    progress_callback=self.update_progress_safe,
                )
                label = ticker
        except Exception as e:
            log.error(
                "GUI: analysis_callback failed for %s: %s", ticker_sel, e, exc_info=True
            )
            result = (False, 0.0)
            label = ticker_sel

        self.root.after(0, self.finalize_analysis, result, label)

    # ------------------------------------------------------------------
    # UI updates
    # ------------------------------------------------------------------

    def finalize_analysis(self, result: Tuple[bool, float], ticker: str) -> None:
        """Handle completion on UI thread."""
        success, hint_value = result

        if success:
            done_label = "all tickers" if ticker == self.ALL_TICKERS_LABEL else ticker
            self.update_progress(100, f"Plot for {done_label} saved. Ready.")
            if hint_value and float(hint_value) > 0.0:
                self.delta_atr_var.set(f"Typical Δ(ATR(14)): ±{float(hint_value):.4f}")
            else:
                self.delta_atr_var.set("Δ(ATR(14)): (Run analysis to calculate)")

            messagebox.showinfo(
                "Success",
                f"Analysis for {done_label} is complete and outputs have been saved.",
            )
        else:
            self.update_progress(0, "Failed. Ready.")
            self.delta_atr_var.set("Δ(ATR(14)): (Run analysis to calculate)")
            messagebox.showwarning(
                "Failure",
                f"Analysis for {ticker} failed or was cancelled. See logs for details.",
            )

        self.analyze_button.config(state=tk.NORMAL)

    def update_progress(self, value: int, phase: str) -> None:
        """Update progress bar and status label (UI thread)."""
        v = int(max(0, min(100, int(value))))
        self.progress_bar["value"] = v
        self.status_label["text"] = f"Status: {phase} [{v}%]"

    def update_progress_safe(self, value: int, phase: str) -> None:
        """Thread-safe progress update."""
        self.root.after(0, self.update_progress, value, phase)


# ----------------------------------------------------------------------
# Convenience runner (optional)
# ----------------------------------------------------------------------


def run_gui(analysis_callback: Callable[..., Tuple[bool, float]]) -> None:
    """
    Convenience entrypoint. Main app can call:

        from src.ui.gui import run_gui
        run_gui(analysis_callback=my_pipeline)
    """
    root = tk.Tk()
    _ = StockAnalysisApp(root, analysis_callback=analysis_callback)
    root.mainloop()


__all__ = ["StockAnalysisApp", "run_gui"]
