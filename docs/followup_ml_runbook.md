# Follow-up ML Runbook

This runbook describes the weekly no-Excel operating flow for Follow-up ML artifacts.

## Scope

- T0 draft generation
- T+3 finalization and scoring
- AVR memory and next-weight export
- Parity fixture snapshot and compare

## Prerequisites

- Run from repo root.
- Use active project virtual environment.
- Use the venv interpreter explicitly when needed: `/repo/.venv/bin/python`.
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

## SOP Execution Checklist (M5)

Use this checklist for the required weekly sequence:

```bash
ROUND_ID=26-1-11
PYTHON=${PYTHON:-/repo/.venv/bin/python}
"$PYTHON" scripts/followup_ml.py draft --round-id "$ROUND_ID"
"$PYTHON" scripts/followup_ml.py finalize --round-id "$ROUND_ID"
"$PYTHON" scripts/followup_ml.py board --round-id "$ROUND_ID"
"$PYTHON" scripts/followup_ml_parity.py compare --round-id "$ROUND_ID"
```

Required validations before publish:

- `draft` produced round artifacts and dashboard markdown for `ROUND_ID`.
- `finalize` produced partial/final scores with no production override flags.
- `board` refreshed `dashboard/<round_id>.md` and `dashboard/latest.md`.
- parity compare report exists and indicates pass for required fixtures.
- CI gate `followup-ml-gate` is green for the commit being published.

Required evidence capture (non-author run):

- A non-author operator executes the full sequence above.
- Record operator, date, commit SHA, and exact commands in `docs/followup_ml_m5_evidence_pack.md`.
- Attach links to parity report, CI run, and publish proof in the same evidence entry.
- If any step fails, stop publish and log issue/fix notes before retry.

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

- verify unapproved expansion merges = 0
- record exceptions and approvals in evidence pack

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
