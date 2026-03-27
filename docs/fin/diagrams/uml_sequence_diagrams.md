# UML Sequence Diagrams

## Sequence 1: GUI Analysis Run (`scripts/app3G.py`)

```mermaid
sequenceDiagram
  autonumber
  participant User
  participant GUI as src.ui.gui.StockAnalysisApp
  participant Orchestrator as scripts/app3G.py
  participant Loader as src.data.loading.fetch_data
  participant TIWorker as scripts/workers/app3GTI.py
  participant Models as src.models.compat_api.compute_forecasts
  participant Snap as src.utils.calc_snapshots
  participant FS as out/i_calc + graphs

  User->>GUI: Click Analyze
  GUI->>Orchestrator: run_analysis(params)
  Orchestrator->>Loader: load raw OHLCV
  Loader-->>Orchestrator: base dataframe
  Orchestrator->>TIWorker: subprocess request (context csv args)
  TIWorker-->>Orchestrator: enriched CSV path
  Orchestrator->>Models: compute_forecasts(enriched_df, exo_config)
  Models-->>Orchestrator: per-model forecast artifacts
  Orchestrator->>Snap: write snapshot artifacts
  Snap->>FS: write csv/json/md
  Orchestrator-->>GUI: summary, final path, metrics
  GUI-->>User: tables + charts updated
```

## Sequence 2: DynaMix Worker Protocol

```mermaid
sequenceDiagram
  autonumber
  participant Facade as src.models.dynamix.predict_dynamix
  participant Tmp as tempfile workspace
  participant Worker as scripts/workers/dynamix_worker.py
  participant DynRepo as external DynaMix repo
  participant CSV as artifact_csv

  Facade->>Tmp: write context.csv
  Facade->>Worker: spawn subprocess --context-csv --artifact-csv
  Worker->>DynRepo: run forecast engine
  DynRepo-->>Worker: predictions
  Worker->>CSV: write forecast.csv
  Worker-->>Facade: JSON payload {ok, artifact_csv, error?}

  alt payload ok and artifact readable
    Facade->>CSV: read forecast csv
    Facade-->>Facade: normalize columns/index
    Facade-->>Facade: return dataframe
  else payload invalid or failed
    Facade-->>Facade: log warning and return None
  end
```

## Sequence 3: Follow-up ML Draft and Finalize

```mermaid
sequenceDiagram
  autonumber
  participant CLI as scripts/followup_ml.py
  participant Draft as src.followup_ml.draft
  participant Models as src.models.compat_api
  participant Out as out/i_calc/followup_ml
  participant VG as src.followup_ml.vg_store

  CLI->>Draft: draft(round_id, tickers, run_mode)
  Draft->>Models: compute t0 forecasts and metrics
  Models-->>Draft: model outputs
  Draft->>Out: write t0_forecasts, t0_draft_metrics, day3_matrix, context_json
  Draft-->>CLI: DraftArtifacts

  CLI->>Draft: finalize(round_id, lookup_date_override)
  Draft->>Out: load context and draft artifacts
  Draft->>Out: write actuals, partial_scores, model_summary, avr, weights
  Draft-->>CLI: FinalizeArtifacts

  CLI->>VG: ingest_round_from_artifacts(round_id)
  VG->>Out: read context and partial scores
  VG->>VG: upsert rounds and violet scores in sqlite
  VG-->>CLI: ingestion summary
```

## Sequence 4: TDA Export with Degradation Path

```mermaid
sequenceDiagram
  autonumber
  participant CLI as scripts/tda_export.py
  participant Loader as src.data.loading.fetch_data
  participant TDA as src.structural.tda_indicators
  participant Ripser as ripser (optional dep)
  participant Out as out/i_calc

  CLI->>Loader: fetch_data for each ticker
  Loader-->>CLI: per-ticker dataframes
  CLI->>TDA: compute_tda_context(ticker_dfs)
  TDA->>Ripser: import and compute persistence

  alt ripser available and enough data
    Ripser-->>TDA: persistence diagrams
    TDA-->>CLI: contexts state=OK or DEGENERATE/INSUFFICIENT_DATA
  else missing ripser
    TDA-->>CLI: contexts state=MISSING_DEP and note
  end

  CLI->>TDA: build_tda_context_markdown + build_tda_metrics_df
  TDA-->>CLI: markdown and metrics dataframe
  CLI->>Out: write tda_context.md and tda_metrics.csv
```
