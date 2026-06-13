# LSTM Calibration — Plan of Record

> **Goal:** Improve the **point-forecast accuracy** of the canonical quantile LSTM
> (`src/models/lstm.py::predict_lstm_quantiles`). Per decision on 2026-06-12, we
> **build a backtest harness FIRST** to capture a clean "before" baseline on the
> *current, unmodified* model, then apply modeling + calibration fixes and prove
> each change reduces error against that baseline.
>
> **Phase-1 constraints (must hold):** canonical logic stays in `src/`; `compat/`
> remains delegation-only; the public `LSTM_Pred / LSTM_Lower / LSTM_Upper`
> contract and `ForecastArtifact` boundary are preserved; behavior stays
> deterministic (fixed seed). The harness itself is a developer/baseline utility,
> so it lives in `tools/` per `AGENTS.md`.

---

## ✅ AS-IS STATUS / SESSION HANDOFF — 2026-06-13

**Where we are:** **Epic 1 is COMPLETE** — harness built/tested/smoke-validated AND
the full baseline captured (Task 1.4 done; readout below in the Task 1.4 section).
Baseline run `CSV_OUTPUT/lstm_baseline/20260613T073854Z/` (1374 scored, 5.8% skip,
valid). **NEXT ACTION: start Epic 2 (median head + OOS de-bias)** — the baseline
shows the dominant defect is systematic under-prediction bias (MBE ≈ 71% of MAE),
not recursive horizon drift, so Epic 2 is the high-leverage fix and Epic 3 is
de-prioritized. All work still **uncommitted** (trunk-only repo). Epic 3 not started.

> **Prior handoff (2026-06-12, superseded):** Epic 1 was built/tested/smoke-validated
> with only Task 1.4 (the baseline run) pending a user decision on ticker set + window.
> That decision was made 2026-06-13 (all 6 tickers, full span, weekly) and the run
> executed — see the Task 1.4 BASELINE READOUT below.

### Environment (ready to use)
- venv: `/home/nekiee/CC_FIN/vEnv` (Python **3.12.13**, built via `uv`).
- Installed `requirements.txt` in full: **torch 2.6.0+cu124, numpy 1.26.4,
  pandas 2.1.4**, scikit-learn, statsmodels, TA-Lib (wheel), pytorch-forecasting, etc.
- **Always invoke with `vEnv/bin/python`** (system python is 3.14, no torch wheels).
- `.gitignore` updated to ignore `vEnv/` (case-sensitive; was uncovered).

### Built this session (all uncommitted — trunk-only repo, nothing committed yet)
| Artifact | State |
|---|---|
| `tools/lstm_backtest.py` | Harness (~530 lines). Done. Smoke-validated. |
| `tests/test_lstm_backtest.py` | 16 tests — **all pass**. |
| `docs/lstm_calibration/00_backtest_baseline_plan.md` | This plan (Tasks 1.1/1.2 specs + status). |
| `.gitignore` | `vEnv/` added. |
| `CSV_OUTPUT/lstm_baseline_smoke/20260612T185620Z/` | Throwaway smoke output (AAPL, 9 pts). |

### Verify-resume commands
```bash
vEnv/bin/python -m pytest tests/test_lstm_backtest.py -q          # expect 16 passed
vEnv/bin/python tools/lstm_backtest.py --help                    # CLI reference
# Guardrail interval tests need compat on path (see Known issue):
PYTHONPATH=compat vEnv/bin/python -m pytest tests/test_interval_harmonization.py -q
```

### Epic 1 task ledger
- 1.1 Verify entrypoint contract — **DONE** (`predict_lstm` @ `compat_api.py:742`; actuals = full-history `fetch_data["Close"]`; leakage `<= as_of` confirmed).
- 1.2 Metrics & schema — **DONE** (formulas + skip taxonomy + locked CSV/JSON schema).
- 1.3 Implement harness — **DONE** (`tools/lstm_backtest.py`, py_compile + smoke OK).
- 1.4 **Capture baseline — NOT DONE.** ← **NEXT ACTION.** Needs ticker set + window.
- 1.5 Harness tests — **DONE** (16 passed).

### ▶️ NEXT ACTION (resume here)
Run the full baseline, then write the readout into Task 1.4 + a per-horizon table:
```bash
vEnv/bin/python tools/lstm_backtest.py \
  --tickers AAPL,DJI,GSPC,QQQ,TNX,VIX \
  --start <YYYY-MM-DD> --end <YYYY-MM-DD> --step 5 \
  --out CSV_OUTPUT/lstm_baseline
```
**Open decisions blocking 1.4:** (a) ticker set — all 6 discovered or subset?
(b) as-of window + step (suggestion: ~weekly over last ~12 months, end ≈ 2026-05-07
so fh=3 actuals exist before data end 2026-05-12). Data range per ticker: ~Jul 2024 → May 2026.
After 1.4 → start **Epic 2 (median head + OOS de-bias)**.

### Known issue (logged, not yet fixed)
`src/models/intervals.py::_discover` uses legacy `import Constants` (resolves only
when `compat/` is on `sys.path`). On a bare `pytest` it makes 3
`test_interval_harmonization.py` tests fail and PI fall back to 0.90/q0.05/q0.95.
- **Harness already mitigates** (its bootstrap adds `compat/` → LSTM runs with
  harmonized 0.86/q0.07/q0.93). Verified.
- **Pre-existing, not from our changes** (diff is only `tools/`,`tests/`,`docs/`,`.gitignore`).
- Follow-up candidate (out of Epic-1 scope): change `_discover` to `import compat.Constants`.

### Early smoke signal (n=9, NOT significant — confirm on full baseline)
Per-horizon MAE 2.98→3.94→4.13 and MBE −0.91→−3.77→−4.13 (recursive under-prediction
drift); coverage 66.7% vs 86%. Tentatively motivates **both** Epic 2 and Epic 3.

---

## Roadmap (epic order)

| # | Epic | State | Why this order |
|---|------|-------|----------------|
| 1 | **Backtest & baseline harness** | **NOW** | Can't claim "less poor" without a measured before/after. No model code changes — zero risk to the contract. |
| 2 | Phase A — median head + out-of-sample de-bias | Planned | Highest impact-to-risk fix for point error; contained to one file. |
| 3 | Phase B — returns-space modeling | Planned | Removes recursive drift, but touches windowing/scaling/recursion — only after A is measured. |

Epics 2–3 are specified at lower resolution here; they will be expanded once the
baseline numbers from Epic 1 tell us *where* the error actually is (bias vs. lag
vs. variance vs. per-horizon decay).

---

# EPIC 1 — LSTM backtest & baseline harness  `[NOW]`

**Outcome:** A deterministic, leakage-safe script that replays a date range,
runs the **unmodified** LSTM per (ticker, as-of date), scores the `fh`-step point
forecast against realized actuals, and writes a versioned baseline report. This
report is the reference every later change is compared against.

**Explanation of approach.** We reuse what already exists rather than re-deriving it:
- `src/data/loading.py::fetch_data(..., as_of_date=...)` already supports an
  as-of cutoff — this is our **leakage guard** (training data must be `<= as_of`).
- The LSTM is invoked through the **canonical path** (`src.models.compat_api` /
  `src.models.facade`) so the backtest scores exactly what production runs — not a
  re-implementation that could drift from real behavior.
- Scoring helpers in `src/followup_ml/draft.py` (e.g. `_compute_partial_scores`)
  and the rounds/actuals reconciliation are reused where they fit; the harness
  only adds metrics they don't already produce.

> **Non-goal for Epic 1:** changing any model behavior. If a task here requires
> editing `src/models/lstm.py`, it's out of scope — push it to Epic 2.

---

### Task 1.1 — Confirm the invocation & actuals contract  `[spike]`

**What:** Verify, by reading code, the exact functions to (a) run a single-model
LSTM forecast for a given ticker + as-of date returning `LSTM_Pred/Lower/Upper`
over `fh` business days, and (b) fetch realized actuals for those forecast dates.

**Why:** The harness must call the *same* canonical entrypoint production uses, and
must look up actuals through the *same* calendar logic (`fh`, business-day
alignment) the rounds system uses — otherwise the baseline is meaningless.

**Changes / artifacts:**
- Short notes appended to this file under "Verified contract" (entrypoint
  signature, actuals lookup function, business-day/`fh` source).

**Acceptance criteria:**
- [ ] The canonical single-model LSTM entrypoint is identified with file:line and
      its return shape documented.
- [ ] The actuals-lookup function (forecast-date → realized value) is identified
      with file:line.
- [ ] `fh` and the business-day calendar source are documented (confirm they match
      `lstm.py::_future_index` / `_as_bday`).
- [ ] Confirmed: `fetch_data(as_of_date=...)` truncates history at the cutoff
      (no look-ahead rows leak into training).

---

### Verified contract (Task 1.1 — completed 2026-06-12)

**Entrypoint (the call the harness will use):**
`src/models/compat_api.py:742`
```python
predict_lstm(
    enriched_data: DataFrame,          # only a "Close" column is required
    ticker: str = "Unknown",
    exo_config: Optional[Any] = None,  # None => no exogenous regressors (clean baseline)
    history_mode: Optional[str] = None,
    progress_callback=None,
) -> Optional[DataFrame]               # None on failure/insufficient history
```
- This is the **canonical production path**: it delegates to
  `src/models/lstm.py::predict_lstm_quantiles` (`compat_api.py:758`). Scoring it
  means scoring exactly what production runs — no re-implementation drift.
- **Return shape:** DataFrame indexed by the next `C.FH` **business days**, columns
  **`LSTM_Pred`, `LSTM_Lower`, `LSTM_Upper`**, sliced to `C.FH` rows
  (`compat_api.py:836-840`). Matches the contract we must preserve.
- **Input:** raw `fetch_data` output works directly — only `Close` is needed when
  `exo_config=None` (`compat_api.py:752`). No enrichment step required for the
  baseline.

**Forecast horizon & calendar:**
- `fh` is **not** a parameter — it is read from `C.FH` (Constants, default 3).
  The harness reports the configured `C.FH`; to sweep horizons we'd set `C.FH`,
  not pass an arg.
- Future dates: `pd.date_range(last_train_date + 1B, periods=C.FH, freq="B")`
  (`compat_api.py:770-774`) — pure business days. **Caveat:** these include market
  holidays, which won't exist in the actuals CSV → those horizon steps are
  skip-and-logged (feeds the skip accounting in Task 1.2/1.3).

**Leakage guard — CONFIRMED safe:**
- `src/data/loading.py::fetch_data(ticker, as_of_date=as_of)` applies
  `df = df.loc[df.index <= cutoff]` (strict `<=`, `loading.py` as-of block).
  Training history is therefore `<= as_of`; forecast dates are business days
  strictly `> as_of`. No look-ahead. The harness will still assert
  `max(train_index) <= as_of < min(forecast_date)` defensively.

**Actuals lookup — decision:**
- The facade does **not** expose LSTM (`MODEL_PRIORITY_DEFAULT =
  (DYNAMIX, ARIMAX, ETS, PCE, RW)`, `facade.py:558`), and the `followup_ml` rounds
  reconciliation is tied to the rounds DB — heavier than needed for a point backtest.
- **Chosen actuals source:** `fetch_data(ticker)` with **no** `as_of_date` (full
  history) → realized `Close` looked up by exact forecast date; missing date
  (holiday/not-yet-realized) → skip-and-log. This is the same sanitized series the
  model trains on, so point error is apples-to-apples and leakage-free (actuals are
  read independently of the truncated training frame).

**Determinism:**
- `predict_lstm` passes `seed=42`; `predict_lstm_quantiles` seeds numpy + torch.
  Deterministic on CPU (the project is CPU-first). GPU/cuDNN paths may introduce
  minor nondeterminism — the harness records `device` from the model `meta` and the
  torch/numpy versions so any nondeterminism is attributable.

**`history_mode` decision:**
- `_select_lstm_training_policy` (`compat_api.py:713`) relaxes `lookback`/`min_samples`
  only when `history_mode == "replay"` and history is short. Because the backtest
  *is* a historical replay, the harness will pass **`history_mode="replay"`** so
  early as-of dates with limited history are scored the way replay/backfill scores
  them, rather than being silently skipped under the stricter "live" policy. (The
  baseline summary records which policy each run used.)

**Implications for the harness (carried into Task 1.3):**
1. Loop builds `enriched_data = fetch_data(ticker, as_of_date=as_of)`; bail/skip if `None`.
2. Call `predict_lstm(enriched_data, ticker, exo_config=None, history_mode="replay")`.
3. Read `C.FH` for horizon; actuals from full-history `fetch_data(ticker)["Close"]`.
4. `last_close = enriched_data["Close"].iloc[-1]` for directional hit-rate.

---

### Task 1.2 — Define metrics & report schema  (completed 2026-06-12)

**What:** Lock the metric formulas, edge-case rules, and the exact CSV/JSON schema.

**Why:** Metrics must isolate the symptom we chose — **point accuracy** — while
still capturing interval behavior so Epic 2's calibration work has a baseline too.
The **per-horizon error curve** is the single most important output: it tells us
whether error is a constant bias (favours Epic 2) or grows with horizon from
recursive drift (favours Epic 3).

#### Sign & symbol conventions
For one scored point — ticker `t`, as-of date `a`, horizon step `h ∈ {1..fh}`,
forecast (trading) date `d_h`:
- `pred` = `LSTM_Pred[d_h]`, `lower` = `LSTM_Lower[d_h]`, `upper` = `LSTM_Upper[d_h]`
- `actual` = realized `Close[d_h]` (full-history lookup, Task 1.1)
- `last_close` = `Close[a]` = last training close
- **Error is `e = pred − actual`** → positive `e` means the model **over-predicts**.

#### Per-point quantities
| Field | Formula | Notes |
|---|---|---|
| `signed_err` | `e = pred − actual` | bias direction |
| `abs_err` | `|e|` | feeds MAE/MedAE |
| `sq_err` | `e²` | feeds RMSE |
| `ape` | `|e| / |actual|` | **NaN if `actual == 0`** (excluded from MAPE) |
| `smape_term` | `2·|e| / (|pred| + |actual|)` | **NaN if `|pred|+|actual| == 0`** |
| `in_interval` | `1` if `lower ≤ actual ≤ upper` else `0` | coverage |
| `interval_width` | `upper − lower` | sharpness |
| `norm_width` | `(upper − lower) / last_close` | scale-free width for cross-ticker aggregation |
| `dir_pred` | `sign(pred − last_close)` | predicted move direction |
| `dir_actual` | `sign(actual − last_close)` | realized move direction |
| `dir_eligible` | `1` if `dir_actual ≠ 0` else `0` | exclude flat days from hit-rate |
| `dir_hit` | `1` if `dir_pred == dir_actual` else `0` | only counted when `dir_eligible == 1` |

#### Aggregate metrics (computed overall, **per-horizon**, and per-ticker)
Let `N` = number of **scored** points in the group.
- **MAE** = `mean(abs_err)`  ← primary point-accuracy metric
- **RMSE** = `sqrt(mean(sq_err))`  ← outlier-sensitive companion
- **MBE (bias)** = `mean(signed_err)`  ← +over / −under; the Epic 2 de-bias target
- **MedAE** = `median(abs_err)`  ← robust to outliers
- **MAPE** = `mean(ape over actual≠0) × 100`  (report excluded-point count)
- **sMAPE** = `mean(smape_term over valid) × 100`  (bounded, symmetric)
- **Directional hit-rate** = `mean(dir_hit over dir_eligible) × 100`
- **Coverage** = `mean(in_interval) × 100`  → compare to **target 86%**
- **Mean interval width** = `mean(interval_width)`; **Mean norm width** = `mean(norm_width)`
- **Run health** = `N_scored`, `N_skipped`, `skip_rate`, skip breakdown by reason

> **Determinism note:** every aggregate is a pure function of the per-point rows,
> which are themselves deterministic given `seed=42` and fixed input CSVs. No metric
> uses sampling or wall-clock state.

#### Skip taxonomy (a "good" score must not hide silent drops)
A point/forecast is **skipped** (not scored) with an explicit `skip_reason`:
- `no_history` — `fetch_data(as_of)` returned `None`/too few rows
- `model_none` — `predict_lstm` returned `None` (insufficient samples, torch missing) → skips all `fh` steps for that (ticker, as_of)
- `no_actual` — forecast date is a holiday / not yet realized → skips that step only
- `nan_pred` — `pred`/`lower`/`upper` non-finite
Skip counts are reported overall and per reason; **Task 1.4 fails the baseline if
`skip_rate` exceeds the agreed threshold (default 10%).**

#### Locked schema — per-point rows (`report.csv`, one row per ticker × as_of × horizon step)
```
run_id, harness_version, seed, torch_version, numpy_version,
ticker, as_of_date, history_mode, fh, horizon_step, forecast_date,
last_close, pred, lower, upper, actual,
signed_err, abs_err, sq_err, ape, smape_term,
in_interval, interval_width, norm_width,
dir_pred, dir_actual, dir_eligible, dir_hit,
status, skip_reason, device, model_meta_json
```
- `status ∈ {scored, skipped}`. Skipped rows carry the keys they have (e.g.
  `as_of_date`, `forecast_date`, `skip_reason`) with metric fields left blank — so
  skips are auditable in the same file, not silently dropped.
- `model_meta_json` = the LSTM `meta` block (lookback, train_window, epochs, qhat,
  pi settings, device, n_samples …) for full provenance of each forecast.

#### Locked schema — `summary.json`
```jsonc
{
  "run": { "run_id", "timestamp", "tool_version", "seed", "history_mode",
           "tickers": [...], "start", "end", "n_as_of_dates", "fh",
           "torch_version", "numpy_version" },
  "overall": { "N_scored", "N_skipped", "skip_rate",
               "MAE", "RMSE", "MBE", "MedAE", "MAPE", "sMAPE",
               "dir_hit_rate", "coverage_pct", "coverage_target": 86.0,
               "mean_interval_width", "mean_norm_width",
               "mape_excluded_points" },
  "per_horizon": [ { "horizon_step": 1, "N", "MAE", "RMSE", "MBE",
                     "MAPE", "sMAPE", "dir_hit_rate", "coverage_pct",
                     "mean_interval_width" }, ... ],   // the key Phase A/B signal
  "per_ticker":  [ { "ticker", "N", "MAE", "RMSE", "MBE", "dir_hit_rate",
                     "coverage_pct" }, ... ],
  "skips": { "no_history", "model_none", "no_actual", "nan_pred" }
}
```
Plus `summary.md` — a human-readable render: the overall block, the **per-horizon
table** (h=1..fh), and the skip breakdown.

**Acceptance criteria:**
- [x] Metric formulas written down with explicit sign convention (`e = pred − actual`).
- [x] Edge cases defined: MAPE excludes `actual==0`; sMAPE guards zero denom;
      directional metric excludes flat (`dir_actual==0`) days; non-finite preds skipped.
- [x] Skip taxonomy enumerated; skips are recorded in-file, not dropped.
- [x] Per-point and `summary.{json,md}` schemas locked in this doc.
- [x] Every metric is a pure, deterministic function of the per-point rows.

---

### Task 1.3 — Implement the harness  `tools/lstm_backtest.py`

**What:** New standalone script. CLI:
`python tools/lstm_backtest.py --tickers AAPL,MSFT --start 2025-01-01 --end 2025-05-01 [--fh 3] [--seed 42] [--out CSV_OUTPUT/lstm_baseline]`

**Why `tools/`:** `AGENTS.md` designates `tools/` for "audits, baselines, developer
utilities" — exactly this. No production path imports it, so it cannot violate the
compat/facade contract.

**Algorithm (per ticker, per as-of date in range):**
1. `df = fetch_data(ticker, as_of_date=as_of)` → history strictly `<= as_of`
   (**leakage guard**).
2. Run the canonical LSTM (entrypoint from Task 1.1) → `fh`-step
   `LSTM_Pred/Lower/Upper` on future business dates.
3. For each forecast date, look up the **realized actual** (actuals lookup from
   Task 1.1). Skip-and-log if an actual doesn't exist yet (e.g. future/holiday).
4. Emit one report row per horizon step; accumulate.
5. After the sweep, compute aggregates (overall + per-horizon) and write
   `report.csv`, `summary.json`, and a human-readable `summary.md`.

**Implementation notes / guardrails:**
- **Determinism:** force `seed=42`; record `torch`/`numpy` versions and the model
  `meta` block (the LSTM already returns rich `meta` — persist it per run).
- **Leakage:** assert `max(training_index) <= as_of` and
  `min(forecast_date) > as_of` for every iteration; fail loud if violated.
- **No model edits:** call the model as-is. If a needed knob is hardcoded
  (e.g. `lstm_units`, `lr` at `compat_api.py:810`), record its value in the report
  but **do not** change it — that's Epic 2.
- **Resilience:** wrap each (ticker, date) in try/except at the harness boundary
  (per `AGENTS.md` boundary-exception rule); a single failure logs and continues,
  it does not abort the sweep.
- **Reproducible window:** the as-of date list is derived from the business-day
  calendar so reruns are identical.

**Acceptance criteria:**
- [ ] Script runs from repo root and is CWD-robust (`AGENTS.md` entrypoint rule).
- [ ] `--help` documents every flag.
- [ ] Produces `report.csv` + `summary.json` + `summary.md` under `--out`.
- [ ] Leakage asserts are present and the run aborts if either is violated.
- [ ] Re-running with the same args reproduces byte-identical metric values.
- [ ] Per-(ticker,date) failures are logged and skipped, not fatal; skip count
      appears in the summary.
- [ ] No file under `src/` or `compat/` is modified by this epic.

**Status (2026-06-12):** `tools/lstm_backtest.py` implemented (~520 lines).
- [x] CWD-robust repo-root bootstrap; imports the canonical `predict_lstm`.
- [x] `--help` / argparse with documented flags and sensible derived defaults
      (all discovered tickers; end = min-last-data − fh BDays; start = end − 60 BDays;
      weekly `--step 5`).
- [x] Writes `report.csv` + `summary.json` + `summary.md` to a timestamped subdir.
- [x] Two leakage asserts (`train_max <= as_of`, `forecast_date > as_of`).
- [x] Per-(ticker,as_of) boundary try/except → skip row, sweep never aborts;
      skip taxonomy + counts emitted.
- [x] No `src/`/`compat/` files modified.
- [x] `python3 -m py_compile` passes (valid syntax).
- [ ] **Live run + byte-identical re-run check BLOCKED:** no venv on this machine
      (`numpy/pandas/torch` absent). Needs `python -m pip install -r requirements.txt`
      in the project venv before Task 1.4 can execute.

---

### Task 1.4 — Capture & commit the baseline

**What:** Run the harness over an agreed (ticker set, date range), commit the
report as the canonical baseline artifact.

**Why:** This frozen artifact is the literal "before" every later epic cites.

**Changes / artifacts:**
- `CSV_OUTPUT/lstm_baseline/<date-range>/report.csv` + `summary.{json,md}`.
- A one-paragraph baseline readout appended to this doc (headline MAE/RMSE/bias,
  per-horizon decay, directional hit-rate, empirical coverage vs 86%).

**Smoke validation (pre-1.4, 2026-06-12):** ran `tools/lstm_backtest.py --tickers
AAPL --start 2026-04-20 --end 2026-05-07 --step 5` → 3 as-of × fh=3 = **9 scored, 0
skipped**, ~20s. Outputs (`report.csv` 32 cols / `summary.{json,md}`) verified:
leakage guard held (forecast_date > as_of), `signed_err = pred − actual` correct,
`in_interval`/`dir_hit` correct. **Early (non-significant, n=9) signal:** MAE rises
with horizon (h1 2.98 → h3 4.13) and MBE is increasingly negative (h1 −0.91 → h3
−4.13) = recursive under-prediction drift; coverage 66.7% vs 86% target (intervals
too narrow, consistent with `LSTM_PI_WIDTH_MULT=0.30`). Previews that **both** Epic 2
(de-bias) and Epic 3 (drift) are in play — to be confirmed on the full window.

**Acceptance criteria:**
- [x] Baseline run completed over the agreed window with <X% skipped forecasts
      (threshold set with user; default: flag if >10% skipped). **5.8% — valid.**
- [x] Summary readout written here, including the **per-horizon error curve** (the
      key signal for deciding Phase A vs Phase B priority).
- [x] Ticker set + date range + tool version recorded so the run is reproducible.

---

### ✅ BASELINE READOUT (Task 1.4 — captured 2026-06-13)

**Run:** `CSV_OUTPUT/lstm_baseline/20260613T073854Z/` (`report.csv` + `summary.{json,md}`).
**Config (reproducible):** tool v1.0.0, torch 2.6.0+cu124, numpy 1.26.4, seed 42,
`history_mode=replay`, fh=3. Tickers **AAPL,DJI,GSPC,QQQ,TNX,VIX**; as-of window
**2024-09-23 → 2026-05-07**, weekly **step 5**. (User decision 2026-06-13: all 6
tickers, full span, weekly. Start = 2024-09-23 so the replay min-samples floor
[`replay_min_samples = max(45, lookback+25)`, `compat_api.py:733`] is met from the
first as-of and the leading weeks aren't lost to `model_none`.)

**Run health:** **1374 scored / 84 skipped = 5.8% skip rate** (threshold 10% → valid).
Skips are fully explained and benign:
- `no_actual` (48): forecast business day is a holiday/non-trading day with no realized Close — per-step skip.
- `error:AssertionError` (36): the leakage guard correctly refusing the **6 Monday
  market holidays** the weekly stride landed on (2025-01-20, 2025-02-17, 2025-05-26,
  2025-09-01, 2026-01-19, 2026-02-16 × 6 tickers). On a Monday-holiday as-of, the
  pandas `freq="B"` forecast index puts `forecast_date[0]` **on the as-of itself**
  (business-day freq ignores exchange holidays), so `min(forecast_date) > as_of`
  fails by design. Not a harness bug; the guard is doing its job.

**Headline (overall):** MAE 298.94 · RMSE 788.82 · MBE **−211.94** · MedAE 12.52 ·
MAPE 5.12% · sMAPE 5.30% · dir-hit 50.4% · coverage **55.2% vs 86% target**.
(Absolute MAE/RMSE/MBE are dominated by the high-price series — DJI ~40k, GSPC ~5k;
MAPE/sMAPE are the scale-free cross-ticker view.)

**Per-horizon error curve (the Phase A vs Phase B decider):**

| h | N | MAE | RMSE | MBE | MAPE % | dir-hit % | coverage % |
|---|---|-----|------|-----|--------|-----------|------------|
| 1 | 474 | 282.85 | 766.19 | −201.84 | 4.89 | 48.8 | 59.5 |
| 2 | 462 | 299.82 | 788.06 | −230.84 | 4.87 | 53.9 | 55.4 |
| 3 | 438 | 315.41 | 813.37 | −202.94 | 5.62 | 48.4 | 50.5 |

**Per-ticker MAPE:** TNX 3.0% · DJI 3.3% · GSPC 4.0% · QQQ 4.4% · AAPL 4.8% · VIX 11.2%.

**Interpretation → epic priority (revises the n=9 smoke read):**
1. **Dominant defect = systematic under-prediction bias, NOT recursive horizon drift.**
   MBE is large/negative at every horizon and bias is **~71% of MAE** overall
   (−211.9 / 298.9). In scale-free MAPE the curve is essentially flat h1→h2
   (4.89→4.87%) with only a mild h3 bump (5.62%). The horizon-decay signal the
   smoke test (n=9) suggested **does not survive** at n=1374.
   → **Promote Epic 2 (median head + OOS de-bias) to the primary fix; de-prioritize
   Epic 3 (returns-space drift removal)** until Epic 2 is measured.
2. **Intervals far too narrow:** coverage 55.2% vs 86%, decaying h1 59.5% → h3 50.5%
   (mean norm width ~0.107) — consistent with `LSTM_PI_WIDTH_MULT=0.30`. Epic 2's
   OOS-conformal `qhat` is the lever here.
3. **Direction ≈ coin-flip** (50.4%; only VIX > 55%) — the point head isn't capturing
   short-horizon direction. Watch dir-hit as a secondary Epic-2 acceptance signal.

**This run is the frozen "before" artifact** every later epic is compared against.

---

### Task 1.5 — Lightweight tests for the harness

**What:** Add focused tests so the *measurement* itself is trustworthy.

**Why:** A buggy backtest is worse than none — it can "prove" a regression is an
improvement. Test the metric math and the leakage guard, not the LSTM.

**Tests (under `tests/`):**
- Metric functions: known inputs → known MAE/RMSE/bias/coverage/dir-hit.
- Leakage guard: a fabricated frame where actuals precede `as_of` must raise.
- Determinism: two runs on a tiny synthetic frame yield identical summaries.
- Skip accounting: a missing-actual case increments the skip counter and does not
  crash.

**Acceptance criteria:**
- [x] `tests/test_lstm_backtest.py` written: 15 tests covering `_sign`, `_score_step`
      (point formulas, direction miss, flat-day ineligibility), `_metric_block`
      (known MAE/RMSE/MBE/coverage/dir-hit), `aggregate` (skip accounting + threshold
      flag), `run_one` (leakage assert, model_none, no_actual, scoring, nan_pred),
      determinism of aggregates, and `resolve_as_of_dates` defaults.
- [x] Tests are **hermetic & torch-independent**: `fetch_data`/`predict_lstm` are
      monkeypatched, so they need neither real CSVs nor torch (stronger than the
      torch-optional bar — they always run once numpy/pandas are present).
- [x] `python3 -m py_compile` passes for the test file.
- [x] **`pytest tests/test_lstm_backtest.py` → 16 passed** (venv: `vEnv/`, Python
      3.12.13, torch 2.6.0+cu124, numpy 1.26.4, pandas 2.1.4).
- [x] Guardrail suite green **when run as production does** (`compat/` importable):
      `test_models_smoke.py` + `test_models_compat_lstm_policy.py` pass; the 3
      `test_interval_harmonization.py` tests pass with `PYTHONPATH=compat` (4 passed).

#### Finding — legacy `import Constants` & PI discovery (env quirk, not a harness bug)
`src/models/intervals.py::_discover` (line ~22) uses a **legacy top-level
`import Constants`**, but in this repo Constants lives at `compat/Constants.py`.
`conftest.py` only puts the **repo root** on `sys.path` (exposes `compat`, not bare
`Constants`), so on a fresh clone `import Constants` fails and PI silently falls back
to `coverage=0.90, q_low=0.05, q_high=0.95` instead of the harmonized
`0.86 / 0.07 / 0.93`. This is why those 3 interval tests fail under a bare
`python -m pytest` on a clean checkout — **pre-existing, independent of this epic**
(my diff touches only `tools/`, `tests/`, `docs/`, `.gitignore`).

**Harness mitigation (no `src/`/`compat/` edits):** `_bootstrap_fin_root()` now also
adds `compat/` to `sys.path`, so the LSTM runs with the **intended harmonized PI**
during the baseline (verified: `discover_pi_settings()` → `coverage=0.860,
q_low=0.070, q_high=0.930`). Without this the coverage diagnostic would be measured
against the wrong PI target. (Point-forecast metrics are ~unaffected since the point
is the symmetric midpoint, but coverage/width would be skewed.)

> A proper repo-level fix (`_discover` importing `compat.Constants`) is **out of
> scope** for Epic 1 (no `src/` edits) — noted here as a follow-up candidate.

---

### Epic 1 — Definition of Done
- [ ] Tasks 1.1–1.5 acceptance criteria met.
- [ ] Baseline artifact committed and readout recorded in this doc.
- [ ] Zero changes to `src/` or `compat/`.
- [ ] `python -m ruff check tools tests` clean for new files.

---

# EPIC 2 — Phase A: median head + out-of-sample de-bias  `[PLANNED]`

**Outcome:** Point forecast comes from a directly-optimized **median (q=0.5) head**
instead of the interval midpoint, and bias/`qhat` are estimated **out-of-sample**.

**Explanation of changes (in `src/models/lstm.py`):**
- `_LSTMQuantileNet`: add a third linear head `q_med`; train all three jointly
  (pinball@0.5 ≡ L1 on the median).
- Recursion + output: set `LSTM_Pred` = median head; keep `Lower/Upper` from
  `q_lo/q_hi`. **Column contract unchanged.**
- Calibration fix: compute residuals on the **validation holdout** (`X_va`, already
  split 85/15) to derive a point **bias correction** and the conformal `qhat`,
  replacing today's in-sample residual computation.

### Tasks (outline)
- 2.1 Add `q_med` head + joint pinball loss. **AC:** all three heads train; loss
  decomposable; determinism preserved.
- 2.2 Use median as `LSTM_Pred`; keep edges. **AC:** output columns/`ForecastArtifact`
  unchanged; smoke + harmonization tests green.
- 2.3 Move residual/bias estimation to the validation split. **AC:** `qhat` computed
  on held-out data; `meta` records `pi_qhat` + new `point_bias`.
- 2.4 Re-run Epic 1 harness. **AC:** MAE **and** bias improve vs baseline on the
  agreed window (no per-horizon regression); coverage no worse than baseline.

### Epic 2 — Definition of Done
- [ ] Point MAE/bias improved vs Epic 1 baseline, contract & determinism intact,
      guardrail tests green, `compat/` untouched (delegation-only).

---

# EPIC 3 — Phase B: returns-space modeling  `[PLANNED]`

**Outcome:** Model **log-returns** instead of raw price levels to kill the recursive
mean-reversion drift that grows with horizon.

**Explanation of changes (in `src/models/lstm.py`):**
- Target transform: `r_t = log(P_t / P_{t-1})`; build windows on returns.
- Scaling: standardize (z-score) returns instead of min-max on price levels; relax
  the `LSTM_SCALED_CLIP` `[-0.2, 1.2]` guard (semantics don't apply to returns).
- Recursion: forecast returns step-by-step; reconstruct price by cumulative product;
  map quantile heads back to price space for `Lower/Upper`.

### Tasks (outline)
- 3.1 Returns transform + window builder. **AC:** exact round-trip reconstruction on
  a known series.
- 3.2 Standardization + clip relaxation. **AC:** no boundary flattening; determinism
  preserved.
- 3.3 Recursive forecast + price reconstruction. **AC:** `fh`-step output preserves
  column contract.
- 3.4 Re-run Epic 1 harness. **AC:** **per-horizon error curve flattens** vs both the
  baseline and Epic 2; overall MAE/RMSE improve.

### Epic 3 — Definition of Done
- [ ] Per-horizon error decay reduced and overall point error improved vs Epic 2,
      contract & determinism intact, guardrail tests green.

---

## Cross-cutting acceptance (all epics)
- [ ] `from __future__ import annotations`; stdlib/third-party/local import grouping
      (`AGENTS.md` style rules).
- [ ] Heavy/optional imports (`torch`) stay gated/local.
- [ ] Deterministic outputs under fixed seed.
- [ ] Targeted `ruff` clean on changed modules; targeted tests for touched areas;
      guardrail tests when touching contracts/adapters.
- [ ] Trunk-only workflow: changes land on `main` per repo policy.

## Open questions for the user
1. **Ticker set + date range** for the baseline window (Task 1.4)? (Drives runtime
   and statistical significance.)
2. **Output location** — `CSV_OUTPUT/lstm_baseline/` acceptable, or a dedicated
   `baselines/` dir?
3. **Acceptable skip threshold** for a valid baseline run (default proposed: 10%)?
