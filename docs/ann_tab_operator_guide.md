# ANN Tab Operator Guide

Last reviewed: 2026-04-11
Source commit: `055c7bc`

This guide explains ANN tab controls, what each button does, which artifacts are read/written, and how to tune parameters safely.

## Info Button

- Location: ANN tab, above `Run ANN Feature Ingest`.
- Behavior:
  - If sidebar ticker is `ALL`, Info shows ANN setup/tuning information for all tickers (`TNX`, `DJI`, `SPX`, `VIX`, `QQQ`, `AAPL`).
  - If sidebar ticker is a single ticker, Info only shows that ticker.
- Data sources used by Info:
  - setup files: `out/i_calc/ANN/<TICKER>.setup.json`
  - latest tuning matrix: `out/i_calc/ANN/tuning/tune_*/best_config_matrix.json`
  - prune profile: `out/i_calc/ann/feature_profiles/pruned_inputs.json`
  - ANN feature store summary: `out/i_calc/stores/ann_input_features.sqlite`

## Run ANN Feature Ingest

### What it runs

- CLI: `scripts/ann_feature_stores_ingest.py`
- UI wrapper: `src/ui/services/ann_ops.py::run_ann_feature_stores_ingest`

### What it reads

- Technical indicators: `out/i_calc/TI/*.csv`
- Pivot levels: `out/i_calc/PP/*.csv`
- SVL Hurst metrics: `out/i_calc/svl/SVL_METRICS_*.csv`
- TDA H1 metrics: `out/i_calc/tda/TDA_METRICS_*.csv`

### What it writes

- SQLite store: `out/i_calc/stores/ann_input_features.sqlite`
- Family tables:
  - `ann_ti_inputs`
  - `ann_pivot_inputs`
  - `ann_hurst_inputs`
  - `ann_tda_h1_inputs`
- Ingest audit table: `ann_feature_ingest_files`

### How ingest logic works

1. Collect rows from TI/PP/SVL/TDA source files.
2. Normalize fields (`ticker`, `as_of_date`, `feature_name`, `feature_value`, `source_family`).
3. Upsert rows by `(as_of_date, ticker, feature_name)` for deterministic overwrite of same keys.
4. Update family-level counts and latest as-of metadata.
5. Print run summary to stdout; ANN tab shows command/stdout/stderr.

### When to use

- Use this after upstream indicator exports have been refreshed.
- This is the canonical ANN feature ingestion path for training/tuning datasets.

## Run ANN Marker Ingest (Legacy)

### What it runs

- CLI: `scripts/ann_markers_ingest.py`
- UI wrapper: `src/ui/services/ann_ops.py::run_ann_markers_ingest`

### What it reads

- Markdown-style marker files: `data/raw/ann/*.txt`

### What it writes

- SQLite store: `out/i_calc/stores/ann_markers_store.sqlite`
- Tables:
  - `ann_marker_ingest_files`
  - `ann_marker_values`

### How ingest logic works

1. Discover date-stamped files (`YYYY-MM-DD.txt`).
2. Parse marker rows/ticker columns from table lines.
3. Normalize marker names into canonical names (`RD`, `85220`, `MICHO`, close markers).
4. Upsert by `(as_of_date, ticker, marker_name_canonical)`.
5. Record ingest metadata and print a per-file result summary.

### Legacy scope note

- Marker ingest maintains the marker store for legacy workflows and diagnostics.
- ANN feature training pipeline uses the ANN input feature store from `Run ANN Feature Ingest`.

## Parameter Guide

### Window Length

- UI field: `Window Length`
- CLI flag: `--window-length`
- Effect: controls the lookback window used during ANN dataset construction.
- Practical tradeoff:
  - Larger window = richer temporal context.
  - Larger window also reduces usable sample count on short history.

### Lag Depth

- UI field: `Lag Depth`
- CLI flag: `--lag-depth`
- Effect: number of lagged copies generated for each feature.
- Practical tradeoff:
  - Higher lag depth can improve time-pattern capture.
  - Higher lag depth increases feature count and overfit risk on small datasets.

### Tune Max Trials

- UI field: `Tune Max Trials`
- CLI flag: `--max-trials`
- Effect: random search budget in `scripts/ann_tune.py`.
- Practical tradeoff:
  - More trials increase chance of better configs.
  - Runtime scales roughly with trials x setups x validation folds.

### Prune Keep Ratio

- UI field: `Prune Keep Ratio`
- CLI flag: `--importance-keep-ratio`
- Used by: `Prune Inputs` (importance feature-selection mode).
- Effect: keeps this fraction of top-ranked features.
- Example: `0.50` keeps approximately 50% of features after ranking.

## Button Guide

### Prune Inputs

- Runs ANN training in feature-selection mode:
  - `--feature-selection importance`
  - `--importance-keep-ratio <Prune Keep Ratio>`
  - `--save-selected-features-file out/i_calc/ann/feature_profiles/pruned_inputs.json`
- Ticker scope:
  - `ALL` sidebar = all tickers.
  - Single sidebar ticker = only that ticker.
- Result:
  - Writes/updates prune profile file with selected features.

### Run ANN Train

- Runs `scripts/ann_train.py` using current UI controls:
  - window length, lag depth, train end date, target mode, ticker scope.
- If prune profile exists, training includes:
  - `--feature-allowlist-file out/i_calc/ann/feature_profiles/pruned_inputs.json`
- Output:
  - training artifacts under `out/i_calc/ANN/training/run_*`
  - ANN tab may show top input impacts when available.

### Run ANN Tune

- Runs `scripts/ann_tune.py --max-trials <Tune Max Trials>`.
- Output:
  - tuning artifacts under `out/i_calc/ANN/tuning/tune_*`
  - includes `trials.csv`, `best_config.json`, `best_summary.json`, and matrix output when matrix mode is used.

### Reset ANN

- Deletes prune profile file when present:
  - `out/i_calc/ann/feature_profiles/pruned_inputs.json`
- Returns ANN training inputs to full feature set.
