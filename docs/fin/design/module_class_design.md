# Python Module and Class Design

Last reviewed: 2026-04-11
Source commit: `055c7bc`

This document captures folder responsibilities, module ownership, and major class/entity contracts for FIN.

## Folder Structure and Responsibilities

```text
opencode-FIN/
  src/
    config/        # path constants, environment bootstrap
    data/          # canonical data loading and raw CSV resolution
    exo/           # exogenous regressor spec and validation
    models/        # forecast model implementations and orchestration contracts
    structural/    # SVL and TDA context computation and exports
    followup_ml/   # draft/finalize flow, VG stores, scope audit
    ann/           # ANN dataset, feature selection, training, metrics
    review/        # review state, exports, consensus, repository services
    ui/            # desktop + streamlit UI surfaces and operational services
    utils/         # compatibility gates, pivots, artifact snapshots
  compat/          # legacy import stability layer delegating to src/
  scripts/         # operational CLI entrypoints
    workers/       # subprocess workers for heavy/isolated model paths
  tests/           # unit, contract, and parity tests
  data/            # raw ticker/exo inputs
  config/          # config CSVs (transform/value assign)
  out/             # generated artifacts and sqlite stores
```

## Module Responsibility Map (Core Runtime)

| Module | Responsibility | Key Public Surface |
|---|---|---|
| `src/config/paths.py` | Canonical path and env resolution | path constants, `load_dotenv_if_present` |
| `src/data/loading.py` | Raw ticker CSV resolution and loading | `resolve_raw_csv_path`, `fetch_data` |
| `src/exo/exo_config.py` | Exogenous model/ticker column selection spec | `ExoSpec`, `load_exo_config` |
| `src/exo/exo_validator.py` | Exogenous data quality and run validation | `ValidationParams`, `validate_exo_config_for_run` |
| `src/models/facade.py` | Primary forecast facade and model selection | `ForecastArtifact`, `ForecastBundle`, `compute_forecasts` |
| `src/models/compat_api.py` | Legacy-compatible orchestration and worker bridges | `compute_forecasts`, legacy worker adapters |
| `src/models/arimax.py` | SARIMAX/ARIMAX forecast path | `ARIMAXResult`, `predict_arimax`, `predict_arima` |
| `src/models/lstm.py` | Torch LSTM quantile forecasting | `LSTMResult`, `predict_lstm_quantiles` |
| `src/models/pce_narx.py` | Polynomial chaos + NARX forecast path | `PCENARXResult`, `predict_pce_narx` |
| `src/models/dynamix.py` | DynaMix subprocess-backed forecast path | `DynaMixResult`, `predict_dynamix` |
| `src/models/ets.py` | Exponential smoothing forecast | `ETSResult`, `predict_ets` |
| `src/models/random_walk.py` | Baseline random-walk forecast with intervals | `RandomWalkResult`, `predict_random_walk` |
| `src/models/var.py` | VAR multivariate forecast path | `VARResult`, `predict_var` |
| `src/models/garch.py` | GARCH/ARX-GARCH volatility path | `GARCHResult`, `predict_garch_arx` |
| `src/models/intervals.py` | Shared prediction interval policy | `PISettings`, `discover_pi_settings` |
| `src/structural/svl_indicators.py` | Hurst/Trend/Williams structural context | `TickerStructuralContext`, exports |
| `src/structural/tda_indicators.py` | Topological state metrics and markdown/csv | `TickerTDAContext`, `compute_tda_context` |
| `src/followup_ml/draft.py` | Follow-up round draft/finalize lifecycle | `DraftArtifacts`, `FinalizeArtifacts` |
| `src/followup_ml/vg_store.py` | SQLite ingestion/materialization for ML VG | `initialize_vg_db`, `materialize_vbg_for_date` |
| `src/followup_ml/llm_vg_store.py` | SQLite ingestion/materialization for LLM VG + markers | `initialize_llm_vg_db`, `materialize_llm_vbg_for_date` |
| `src/followup_ml/scope_audit.py` | Governance scope-label audit logic | `PullRequestRef`, `ScopeAuditResult`, `run_scope_audit` |
| `src/ann/config.py` | ANN run/tuning configuration model | ANN config loaders and defaults |
| `src/ann/dataset.py` | ANN dataset assembly and window/lag transforms | dataset build helpers |
| `src/ann/feature_selection.py` | ANN feature pruning strategies | correlation/importance/RFE selectors |
| `src/ann/trainer.py` | ANN model training and evaluation execution | train/evaluate orchestration |
| `src/ann/metrics.py` | ANN metrics and reporting helpers | regression/classification metrics |
| `src/review/service.py` | Review orchestration and chain execution | review pipeline services |
| `src/review/repository.py` | Review data access and persistence bridges | repository read/write helpers |
| `src/review/exports.py` | Review artifact export logic | export helpers |
| `src/review/consensus.py` | Consensus and aggregation logic for review | consensus helpers |
| `src/review/state_map.py` | Runtime state mapping for review/streamlit | state mapping helpers |
| `src/ui/gui.py` | Desktop UI orchestration and rendering | `StockAnalysisApp`, `main` |
| `src/ui/review_streamlit.py` | Streamlit operations console | streamlit app entrypoint |
| `src/ui/services/pipeline_runner.py` | Streamlit pipeline execution service | pipeline runner helpers |
| `src/ui/services/run_registry.py` | Streamlit run registry management | registry loaders/writers |
| `src/ui/services/pipeline_qa.py` | Streamlit QA checks for pipeline runs | QA checks and summaries |
| `src/ui/services/ann_ops.py` | ANN operation wrappers for streamlit UI | ingest/train/tune/reset wrappers |
| `src/utils/compat.py` | Optional dependency feature flags | `HAS_*` gates |
| `src/utils/calc_snapshots.py` | Snapshot writing for run artifacts | snapshot helpers |
| `src/utils/pivots.py` | Pivot-level computations and formatting | `PivotCalcResult`, pivot functions |

## Compatibility Layer Design (`compat/`)

- Purpose: preserve historical import paths while canonical code remains in `src/`.
- Design constraints:
  - Delegation-only behavior for migrated modules.
  - No heavy model dependency imports in `compat/`.
  - Thin function bodies, enforced by tests.

Representative adapters:
- `compat/Models.py` -> re-exports from `src.models.compat_api`.
- `compat/StructuralIndicators.py` -> re-exports from `src.structural.svl_indicators`.
- `compat/TDAIndicators.py` -> delegates to `src.structural.tda_indicators`.
- `compat/Pivots.py` -> delegates to `src.utils.pivots`.

## Key Runtime Entrypoints (`scripts/`)

| Entrypoint | Function |
|---|---|
| `app3G.py` | root shim, path bootstrap, runtime compatibility patch, delegates to `scripts/app3G.py` |
| `scripts/app3G.py` | main GUI analysis orchestrator |
| `scripts/make_fh3_table.py` | FH=3 canonical multi-ticker table utility |
| `scripts/svl_export.py` | structural context export (markdown + csv) |
| `scripts/tda_export.py` | TDA context export (markdown + csv) |
| `scripts/followup_ml.py` | follow-up draft/finalize CLI runner |
| `scripts/followup_ml_vg.py` | ML VG store ingest/materialize CLI |
| `scripts/followup_llm_vg.py` | LLM VG and marker ingest/materialize CLI |
| `scripts/followup_ml_parity.py` | fixture snapshot/compare parity harness |
| `scripts/followup_ml_scope_audit.py` | governance scope audit CLI |
| `scripts/review_streamlit.py` | streamlit launcher for review operations |
| `scripts/streamlit_full_chain.py` | batch chain streamlit utility entrypoint |
| `scripts/ann_feature_stores_ingest.py` | ANN input feature store ingestion |
| `scripts/ann_train.py` | ANN training CLI |
| `scripts/ann_tune.py` | ANN tuning CLI |
| `scripts/ann_markers_ingest.py` | ingest ANN marker markdown tables into sqlite |

## Entity Catalog (Dataclasses and Enums)

| Entity | Kind | Module | Role |
|---|---|---|---|
| `ForecastArtifact` | dataclass | `src/models/facade.py` | model output contract (pred_df + provenance) |
| `ForecastBundle` | dataclass | `src/models/facade.py` | aggregate of per-model artifacts and final selection |
| `ARIMAXResult` | dataclass | `src/models/arimax.py` | ARIMAX output and residual metadata |
| `LSTMResult` | dataclass | `src/models/lstm.py` | Torch LSTM quantile output and training metadata |
| `PCENARXResult` | dataclass | `src/models/pce_narx.py` | PCE-NARX output and run metadata |
| `DynaMixResult` | dataclass | `src/models/dynamix.py` | DynaMix output and worker run metadata |
| `ETSResult` | dataclass | `src/models/ets.py` | ETS output contract |
| `GARCHResult` | dataclass | `src/models/garch.py` | GARCH output contract |
| `VARResult` | dataclass | `src/models/var.py` | VAR output contract |
| `RandomWalkResult` | dataclass | `src/models/random_walk.py` | random walk output contract |
| `PISettings` | dataclass | `src/models/intervals.py` | shared PI policy settings |
| `ExoSpec` | dataclass | `src/exo/exo_config.py` | model/ticker exogenous column policy |
| `ValidationParams` | dataclass | `src/exo/exo_validator.py` | validation thresholds for exogenous checks |
| `WilliamsSignal` | dataclass | `src/structural/svl_indicators.py` | last-active Williams signal |
| `HurstPack` | dataclass | `src/structural/svl_indicators.py` | H20/H60/H120 and regime history package |
| `TickerStructuralContext` | dataclass | `src/structural/svl_indicators.py` | per-ticker SVL export unit |
| `TDAState` | enum | `src/structural/tda_indicators.py` | TDA computation state |
| `TickerTDAContext` | dataclass | `src/structural/tda_indicators.py` | per-ticker TDA export unit |
| `PivotCalcResult` | dataclass | `src/utils/pivots.py` | pivot package used by UI/compat layer |
| `_Defaults` | dataclass | `src/ui/gui.py` | GUI default parameters |
| `DraftArtifacts` | dataclass | `src/followup_ml/draft.py` | draft-phase artifact paths |
| `FinalizeArtifacts` | dataclass | `src/followup_ml/draft.py` | finalize-phase artifact paths |
| `PullRequestRef` | dataclass | `src/followup_ml/scope_audit.py` | PR metadata for scope audit |
| `ScopeAuditResult` | dataclass | `src/followup_ml/scope_audit.py` | audit output package |
| `TDAModule` | dataclass | `scripts/tda_export.py` | runtime TDA module loader contract |
| `ExportPaths` | dataclass | `scripts/tda_export.py` | generated output path package |
| `WorkerInput` | dataclass | `scripts/workers/pce_worker.py` | worker JSON input payload contract |

## Design Constraints Observed in Current Codebase

- Forecast horizon (`FH`) is discovered from `compat/Constants.py` where available, with module-level defaults.
- Optional heavy dependencies are gated via `src/utils/compat.py` and module-local lazy imports.
- Many model paths are best-effort: return `None` on dependency absence/data insufficiency, then fallback selection is applied.
- Follow-up pipelines are artifact-driven and stateful, persisted under `out/i_calc/followup_ml/*` and sqlite stores.
- Streamlit operations are service-oriented (`src/ui/services/*`) and backed by `src/review/*` domain modules.
