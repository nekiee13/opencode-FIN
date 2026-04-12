# Follow-up ML Runbook

Last reviewed: 2026-04-11
Source commit: `055c7bc`

This runbook describes the weekly no-Excel operating flow for Follow-up ML artifacts.

## Scope

- T0 draft generation
- T+3 finalization and scoring
- AVR memory and next-weight export
- Parity fixture snapshot and compare

## Prerequisites

- Run from repo root.
- Use active project virtual environment.
- Raw ticker CSVs present in `data/raw/tickers`.

## Paths

Canonical output root:

- `out/i_calc/followup_ml/`

Subdirectories:

- `rounds/` - round-level artifacts
- `actuals/` - global copy of actuals snapshots
- `scores/` - partial/final score artifacts
- `avr/` - AVR history and round AVR summary
- `weights/` - next-weight exports
- `dashboard/` - per-round markdown board + `latest.md`
- `reports/` - parity compare reports

## Weekly Workflow

### 1) T0 draft

```bash
python scripts/followup_ml.py draft --round-id 26-1-11
```

Writes:

- `round_context.json`
- `t0_forecasts.csv`
- `t0_draft_metrics.csv`
- `t0_day3_matrix.csv`
- `t0_day3_weighted_ensemble.csv` (if prior weights exist)
- dashboard markdown `dashboard/<round_id>.md`

### 2) T+3 finalize (strict production default)

```bash
python scripts/followup_ml.py finalize --round-id 26-1-11
```

Default behavior:

- strict date matching (`actual_date == expected +3 date`)

Optional evaluation/backtest override (break-glass, explicit ack required):

```bash
python scripts/followup_ml.py finalize --round-id 26-1-11 --actual-lookup-date 2026-02-17 --allow-lookup-override --override-reason "benchmark backtest" --override-ticket CHG-123 --override-approver ops_lead
```

Override mode is blocked by default unless `--allow-lookup-override` and all ack fields are provided.
Override mode is marked in context/dashboard as test mode.

### 3) Board re-render

```bash
python scripts/followup_ml.py board --round-id 26-1-11
```

### 4) Parity compare against fixture

```bash
python scripts/followup_ml_parity.py compare --round-id 26-1-11
```

### 5) Publish

- Publish `dashboard/latest.md` and round artifacts after parity pass.
- Do not publish when parity fails or CI gate is red.
- For override/backtest runs, do not publish to production destinations.

## VBG Database (Violet/Blue/Green)

Canonical sqlite path:

- `out/i_calc/ML/ML_VG_tables.sqlite`

Initialize schema and seed default transform policy:

```bash
python scripts/followup_ml_vg.py init-db
```

Ingest one finalized round:

```bash
python scripts/followup_ml_vg.py ingest-round --round-id 26-1-11
```

Materialize violet/blue/green tables for one forecast date:

```bash
python scripts/followup_ml_vg.py materialize --forecast-date 2026-02-27 --write-dir out/i_calc/ML/vg_exports
```

Seed four deterministic debug green snapshots (for warm-up verification):

```bash
python scripts/followup_ml_vg.py seed-green-dummy
```

Seeded dates and values:

- `2000-01-03`: `99.1`
- `2000-01-10`: `99.2`
- `2000-01-17`: `99.3`
- `2000-01-24`: `99.4`

Optional controls:

- `--policy-name <name>`
- `--memory-tail <N>`
- `--bootstrap-enabled` / `--bootstrap-disabled`
- `--bootstrap-score <float>`

Current baseline policy:

- **Blue transform default**: `step_floor` mapping over `config/followup_ml_value_assign.csv` anchor points.
- **Real data start boundary**: `2025-07-29`.
- **Green warm-up**: uses `memory_tail` historical transformed scores; if history is shorter than tail, remaining slots are filled by bootstrap score.

Date anchor rule for GUI operations:

- `selected_date` in GUI is the primary anchor.
- VG target forecast date is resolved from FH3 artifact rows where `AsOf_Cutoff == selected_date` (uses `FH_Date1`).
- If no FH3 artifact match exists, fallback remains `selected_date` (no implicit date drift).

Warm-up examples with `memory_tail=4`:

- `2025-07-29`: real slots `0`, bootstrap slots `4`
- `2025-08-05`: real slots `1`, bootstrap slots `3`
- `2025-08-12`: real slots `2`, bootstrap slots `2`

For Streamlit operations, supported warm-up depth options are `3`, `4`, and `5`.

VG structured debug logs are written to:

- `out/i_calc/gui_ops/vg/*.json`

Current stages:

- `ingest_preflight` / `ingest_result` / `ingest_error`
- `materialize_preflight` / `materialize_result` / `materialize_error`
- `seed_green_preflight` / `seed_green_result`

## LLM VBG and Markers Databases

Canonical sqlite paths:

- `out/i_calc/LLM/LLM_VG_tables.sqlite`
- `out/i_calc/Markers.sqlite`

Initialize databases:

```bash
python scripts/followup_llm_vg.py init-db
python scripts/followup_llm_vg.py init-markers-db
```

Ingest one LLM model markdown table (range+actual cells; actual value is extracted):

```bash
python scripts/followup_llm_vg.py ingest-model-table --forecast-date 2026-02-17 --round-id 26-1-06 --table-file /path/to/llm_table.md
```

Ingest one marker markdown table:

```bash
python scripts/followup_llm_vg.py ingest-markers-table --forecast-date 2026-02-17 --table-file /path/to/markers_table.md
```

Materialize LLM predicted/violet/blue/green outputs:

```bash
python scripts/followup_llm_vg.py materialize --forecast-date 2026-02-17 --write-dir out/i_calc/LLM/vg_exports
```

Policy note:

- LLM green memory uses last `N` available scored observations per canonical model+ticker (missing weeks are skipped).
- Bootstrap fill is applied only when available observations are fewer than `N`.

## ANN Input Feature Stores

Canonical sqlite path:

- `out/i_calc/stores/ann_input_features.sqlite`

ANN input families (used for ANN feature ingestion):

- technical indicators from `out/i_calc/TI/*.csv`
- pivot levels from `out/i_calc/PP/*.csv`
- SVL Hurst current values (`H20/H60/H120`) from `out/i_calc/svl/SVL_METRICS_*.csv`
- TDA CPI metrics (`H1_MaxPersistence`, `H1_CountAbove_Thr`, `H1_Entropy`) from `out/i_calc/tda/TDA_METRICS_*.csv`

TI/PP producers (important):

- `scripts/app3G.py` persists TI/PP snapshots during interactive GUI analysis runs.
- `scripts/ti_pp_backfill.py` is the dedicated replay-date CLI for deterministic TI/PP backfill (no GUI).

Policy note:

- `RD`, `85220`, and `MICHO` are not ANN input features.

Ingest ANN input feature stores (bash):

```bash
python scripts/ann_feature_stores_ingest.py
```

Force reprocess (bash):

```bash
python scripts/ann_feature_stores_ingest.py --force
```

Windows CMD example (from active conda env):

```bat
conda activate F:\vEnv\opencode-FIN
python scripts\ann_feature_stores_ingest.py --force
```

Fully automated replay backfill for ANN ingredients (Windows CMD, one command):

```bat
scripts\ann_ingredients_full_backfill.cmd --start-date 2025-07-29 --end-date 2026-04-07
```

Notes:

- Default mode runs ANN ingest after each date (`--ingest-mode per-date`).
- Use `--ingest-mode end` to ingest only once after all dates complete.
- Pipeline is fail-fast by default; add `--continue-on-error` to keep processing later dates.
- SVL JSON mapping in raw CMD shells must be escaped as `--map-json "{""SPX"":""GSPC""}"` when calling `svl_export.py` directly.

Legacy marker ingest remains available for marker store maintenance only and is not part of ANN input feature ingestion.

### ANN training and tuning

ANN tab operator controls guide:

- `docs/ann_tab_operator_guide.md`

Train one ANN run from current input feature stores:

```bash
python scripts/ann_train.py --tickers TNX DJI SPX VIX QQQ AAPL
```

Key training options:

- `--learning-rate`
- `--scheduler-kind {none,step,cosine,reduce_on_plateau}`
- `--batch-size`
- `--epochs`
- `--early-stopping-patience`
- `--depth` / `--width`
- `--dropout` / `--weight-decay`
- `--window-length` / `--lag-depth`
- `--train-end-date YYYY-MM-DD` (inclusive training cutoff)
- `--target-mode {magnitude,sgn}`

Target mode definitions:

- `magnitude`: `ABS(T0 - P)` where `T0` is ticker close at anchor date and `P` is weighted forecast from model outputs + green weights.
- `sgn`: trend-survival label using `T0`, `P`, and future close (`+h`):
  - `+1` when predicted trend survives (`P>T0` and future close `>T0`, or `P<T0` and future close `<T0`)
  - `-1` for all other cases (broken trend prognosis)

Feature-selection options:

- `--feature-selection {none,correlation,importance,rfe}`
- correlation: `--corr-threshold`
- importance pruning: `--importance-keep-ratio`
- recursive elimination: `--rfe-min-features` and `--rfe-drop-count`

Train output artifacts are written under:

- `out/i_calc/ann/training/run_*/`

Core metric output includes:

- `R2`, `MAE`, `RMSE`, `MAPE`, `directional_accuracy`

Run tuning sweep (randomized trial search):

```bash
python scripts/ann_tune.py --max-trials 20
```

Tuning output artifacts are written under:

- `out/i_calc/ann/tuning/tune_*/`
- `trials.csv`
- `best_config.json`
- `best_summary.json`

Windows CMD example (from active conda env):

```bat
conda activate F:\vEnv\opencode-FIN
cd /d F:\xPy\FIN-Git\opencode-FIN
python scripts\ann_train.py --tickers TNX DJI SPX VIX QQQ AAPL --feature-selection rfe --epochs 120
python scripts\ann_tune.py --max-trials 20
```

## Core Artifacts and Columns

### `scores/<round_id>_partial_scores.csv`

- `round_id`
- `ticker`
- `model`
- `forecast_date`
- `expected_actual_date`
- `lookup_actual_date`
- `pred_value`
- `actual_close`
- `accuracy_pct`
- `transformed_score`
- `score_status`
- `transform_status`

Status values:

- `scored`
- `pending_actual`
- `actual_missing`
- `model_unavailable`
- `nan_pred`
- `no_expected_date`

### `scores/<round_id>_model_summary.csv`

- `model`
- `mean_accuracy_pct`
- `mean_transformed_score`
- `scored_tickers`
- `expected_tickers`
- `coverage_ratio`

### `avr/<round_id>_avr_summary.csv`

- `model`
- `latest_round_score`
- `avr4`
- `avr6`
- `rounds_count`
- `next_weight_suggested`

### `weights/<round_id>_next_weights.csv`

- `round_id`
- `model`
- `weight_raw`
- `weight_norm`
- `avr4`
- `avr6`
- `rounds_count`
- `rank`
- `weights_status` (`provisional` or `final`)
- `source_round_state`
- `generated_at`

## Parity Fixture Workflow

Snapshot:

```bash
python scripts/followup_ml_parity.py snapshot --round-id 26-1-11
```

Compare:

```bash
python scripts/followup_ml_parity.py compare --round-id 26-1-11
```

Compare report:

- `out/i_calc/followup_ml/reports/parity_<round_id>.md`

## Stop Expansion Governance (M5)

- Policy reference: `docs/followup_ml_stop_expansion_rules.md`
- Ownership/escalation matrix: `docs/followup_ml_ownership_escalation_matrix.md`
- PRs must carry exactly one scope label: `m5-scope` or `m5-expansion-exception`.
- Exception PRs require complete exception fields and dual approval.

Weekly audit:

- run scope-audit automation:

```bash
python scripts/followup_ml_scope_audit.py --since 2026-03-01 --write-report
```

- verify `violations=0` in command output
- review generated report:
  - `out/i_calc/followup_ml/reports/scope_audit_YYYYMMDD.md`
- record results in `docs/followup_ml_m5_evidence_pack.md`

## Troubleshooting

- **Many models missing for a ticker**
  - Check TI worker diagnostics and raw OHLC formatting.
  - Ensure comma-formatted numerics parse correctly in raw CSV.

- **`actuals_ok=0/6` in finalize**
  - Strict mode may not yet have expected +3 date in raw CSV.
  - Use no override for production; use `--actual-lookup-date` only for evaluation.

- **Parity compare fails on expected dynamic fields**
  - Timestamps and path-like fields are normalized by parity tool.
  - Inspect report row details for first differing file/column.

## M5 Go-live Checklist and Rollback Procedure

### Go-live checklist
- CI gate is green for target commit.
- Parity passes for rounds 26-1-06, 26-1-09, and 26-1-11.
- Benchmark drift register has no open items.
- Non-author runbook validation evidence is recorded.
- Ownership and escalation approvals are recorded.
- Publish destination and rollback targets are verified.

### Weekly export bundle
- `board.md` from `dashboard/<round_id>.md`
- `scores.csv` from `scores/<round_id>_partial_scores.csv`
- `weights.csv` from `weights/<round_id>_next_weights.csv`
- `state.json` from `rounds/<round_id>/round_context.json`

### Rollback procedure
- Snapshot round context, weights files, and dashboard files.
- Restore snapshot files when corruption is detected.
- Verify checksum match before and after restore.
- Re-run parity compare for the affected round.

### Rollback drill evidence
- `out/i_calc/followup_ml/reports/rollback_drill_20260305T230207Z`
- `out/i_calc/followup_ml/reports/parity_26-1-11.md`
