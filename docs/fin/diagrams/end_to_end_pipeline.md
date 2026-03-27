# End-to-End Pipeline Diagrams

## 1) Forecasting and GUI Runtime Pipeline

```mermaid
flowchart LR
  A[data/raw/tickers/*_data.csv] --> B[src/data/loading.fetch_data]
  B --> C[scripts/app3G.py]
  C --> D[scripts/workers/app3GTI.py]
  D --> E[TI-enriched dataframe]

  E --> F[src/models/compat_api.compute_forecasts]
  F --> G1[ARIMAX]
  F --> G2[PCE-NARX]
  F --> G3[LSTM Torch]
  F --> G4[DynaMix worker]
  F --> G5[ETS/RW/VAR/GARCH]

  G1 --> H[ForecastArtifact candidates]
  G2 --> H
  G3 --> H
  G4 --> H
  G5 --> H

  H --> I[src/models/facade selection]
  I --> J[src/utils/calc_snapshots]
  J --> K[out/i_calc/* csv snapshots]
  I --> L[src/ui/gui charts and summary]
  L --> M[graphs/*]
```

## 2) Structural Context Export Pipeline (SVL/TDA)

```mermaid
flowchart TB
  A[scripts/svl_export.py] --> B[src/data/loading.fetch_data]
  B --> C[src/structural/svl_indicators.compute_structural_context_for_ticker]
  C --> D[SVL markdown + metrics dataframe]
  D --> E[out/i_calc/structural_context.md]
  D --> F[out/i_calc/structural_metrics.csv]

  G[scripts/tda_export.py] --> H[src/data/loading.fetch_data]
  H --> I[src/structural/tda_indicators.compute_tda_context]
  I --> J[TDA markdown + metrics dataframe]
  J --> K[out/i_calc/tda_context.md]
  J --> L[out/i_calc/tda_metrics.csv]

  I --> M{ripser available?}
  M -- no --> N[state=MISSING_DEP, degraded metrics]
  M -- yes --> O[state=OK or INSUFFICIENT_DATA/DEGENERATE]
```

## 3) Follow-up ML and VG Materialization Pipeline

```mermaid
flowchart LR
  A[scripts/followup_ml.py draft] --> B[src/followup_ml/draft.py]
  B --> C[out/i_calc/followup_ml/rounds/<round_id>/t0_*.csv]
  B --> D[out/i_calc/followup_ml/rounds/<round_id>/round_context.json]

  E[scripts/followup_ml.py finalize] --> B
  B --> F[out/i_calc/followup_ml/scores/*]
  B --> G[out/i_calc/followup_ml/weights/*]
  B --> H[out/i_calc/followup_ml/dashboard/*.md]

  I[scripts/followup_ml_vg.py] --> J[src/followup_ml/vg_store.py]
  C --> J
  D --> J
  J --> K[out/i_calc/ML/ML_VG_tables.sqlite]

  L[scripts/followup_llm_vg.py] --> M[src/followup_ml/llm_vg_store.py]
  N[data/raw/ann/*.txt] --> O[scripts/ann_markers_ingest.py]
  O --> P[out/i_calc/stores/ann_markers_store.sqlite]
  M --> Q[out/i_calc/LLM/LLM_VG_tables.sqlite]
  M --> R[out/i_calc/Markers.sqlite]

  S[scripts/followup_ml_parity.py compare] --> T[tests/fixtures/followup_ml/parity]
  C --> S
  D --> S
  S --> U[out/i_calc/followup_ml/reports/parity_<round_id>.md]
```

## 4) DynaMix Worker Integration Sub-Pipeline

```mermaid
flowchart LR
  A[src/models/dynamix.predict_dynamix] --> B[write temp context.csv]
  B --> C[subprocess scripts/workers/dynamix_worker.py]
  C --> D{worker protocol payload}
  D -- ok=true --> E[artifact_csv path]
  E --> F[read forecast csv]
  F --> G[normalize to DYNAMIX_Pred Lower Upper]
  G --> H[return dataframe]

  D -- ok=false or invalid --> I[log warning]
  I --> J[return None]
```
