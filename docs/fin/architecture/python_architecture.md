# Python Architecture Diagram

This diagram documents the current FIN runtime architecture and ownership boundaries.

```mermaid
flowchart TB
  subgraph EntryPoints[Entrypoints]
    E1[app3G.py root shim]
    E2[scripts/app3G.py GUI orchestrator]
    E3[scripts/make_fh3_table.py]
    E4[scripts/svl_export.py]
    E5[scripts/tda_export.py]
    E6[scripts/followup_ml.py]
    E7[scripts/followup_ml_vg.py]
    E8[scripts/followup_llm_vg.py]
    E9[scripts/ann_markers_ingest.py]
    E10[scripts/followup_ml_scope_audit.py]
  end

  subgraph Compat[compat/ (delegation-only adapter layer)]
    C1[Models.py]
    C2[Data_Loading.py]
    C3[Pivots.py]
    C4[StructuralIndicators.py]
    C5[TDAIndicators.py]
    C6[GUI.py]
    C7[Constants.py]
  end

  subgraph Canonical[src/ (single source of truth)]
    subgraph ConfigData[Config and Data]
      S1[src/config/paths.py]
      S2[src/data/loading.py]
      S3[src/exo/exo_config.py]
      S4[src/exo/exo_validator.py]
    end

    subgraph ForecastCore[Forecasting Core]
      F1[src/models/facade.py]
      F2[src/models/compat_api.py]
      F3[src/models/arimax.py]
      F4[src/models/lstm.py]
      F5[src/models/pce_narx.py]
      F6[src/models/dynamix.py]
      F7[src/models/ets.py]
      F8[src/models/garch.py]
      F9[src/models/var.py]
      F10[src/models/random_walk.py]
      F11[src/models/intervals.py]
    end

    subgraph StructuralCore[Structural Context]
      T1[src/structural/svl_indicators.py]
      T2[src/structural/tda_indicators.py]
    end

    subgraph FollowUp[Follow-up ML and Governance]
      U1[src/followup_ml/draft.py]
      U2[src/followup_ml/vg_store.py]
      U3[src/followup_ml/llm_vg_store.py]
      U4[src/followup_ml/scope_audit.py]
    end

    subgraph UtilsUI[Utilities and UI]
      X1[src/utils/compat.py]
      X2[src/utils/calc_snapshots.py]
      X3[src/utils/pivots.py]
      X4[src/ui/gui.py]
    end
  end

  subgraph Workers[scripts/workers subprocess workers]
    W1[app3GTI.py]
    W2[app3GPC.py]
    W3[pce_worker.py]
    W4[dynamix_worker.py]
  end

  subgraph StoresArtifacts[Data Stores and Artifacts]
    D1[data/raw/tickers/*.csv]
    D2[data/raw/exoregressors/Exo_regressors.csv]
    D3[out/i_calc/TI PP ML FH3]
    D4[out/i_calc/followup_ml/*]
    D5[out/i_calc/ML/ML_VG_tables.sqlite]
    D6[out/i_calc/LLM/LLM_VG_tables.sqlite]
    D7[out/i_calc/Markers.sqlite]
    D8[out/i_calc/stores/ann_markers_store.sqlite]
    D9[graphs/]
    D10[logs/]
  end

  E1 --> E2
  E2 --> C1
  E2 --> C3
  E2 --> C6
  E2 --> X2
  E2 --> D9

  E3 --> C1
  E3 --> S2
  E3 --> D3

  E4 --> C4
  E4 --> S2
  E4 --> D3

  E5 --> T2
  E5 --> S2
  E5 --> D3

  E6 --> U1
  E6 --> D4
  E7 --> U2
  E7 --> D5
  E8 --> U3
  E8 --> D6
  E8 --> D7
  E9 --> D8
  E10 --> U4

  C1 --> F2
  C2 --> S2
  C3 --> X3
  C4 --> T1
  C5 --> T2
  C6 --> X4
  C7 --> S1

  F1 --> F3
  F1 --> F5
  F1 --> F6
  F1 --> F7
  F1 --> F10
  F1 --> F11
  F2 --> F3
  F2 --> F4
  F2 --> F5
  F2 --> F6
  F2 --> W1
  F2 --> W2
  F2 --> W3

  F6 --> W4

  S2 --> D1
  S3 --> D2
  X2 --> D3
  U1 --> D4
  U2 --> D5
  U3 --> D6
  U3 --> D7
  E9 --> D8

  X1 --> F1
  X1 --> F2
  X1 --> T2
```

## Ownership and Runtime Notes

- Canonical runtime logic is in `src/`.
- `compat/` preserves legacy import stability and delegates to canonical modules.
- Forecast orchestration currently spans both `src/models/facade.py` and `src/models/compat_api.py` due Phase-1 migration compatibility.
- Worker protocol maturity is mixed:
  - Structured JSON stdout envelope: DynaMix worker.
  - JSON in/out file envelope: PCE worker.
  - Legacy stdout CSV-path contract: TI and Torch workers.
