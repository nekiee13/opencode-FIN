# Follow-up ML Parity Fixtures

This directory stores round-level benchmark fixtures used to compare Python outputs
against approved baseline values (historically sourced from Excel workflow checks).

## Layout

- `manifest.json` - fixture index and metadata
- `<round_id>/` - per-round snapshot folder

Per-round files (when available):

- `round_context.json`
- `t0_forecasts.csv`
- `t0_draft_metrics.csv`
- `t0_day3_matrix.csv`
- `t0_day3_weighted_ensemble.csv`
- `actuals_tplus3.csv`
- `partial_scores.csv`
- `model_summary.csv`
- `avr_summary.csv`
- `next_weights.csv`
- `dashboard.md`

## Generate a fixture snapshot

From repo root:

```bash
python scripts/followup_ml_parity.py snapshot --round-id 26-1-09
```

This copies current artifacts from `out/i_calc/followup_ml/...` into
`tests/fixtures/followup_ml/parity/<round_id>/` and updates `manifest.json`.

## Compare current artifacts against fixture

```bash
python scripts/followup_ml_parity.py compare --round-id 26-1-09
```

Outputs a parity report to:

- `out/i_calc/followup_ml/reports/parity_<round_id>.md`
