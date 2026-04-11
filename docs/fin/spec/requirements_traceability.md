# Requirements Traceability Matrix

Last reviewed: 2026-04-11
Source commit: `055c7bc`

This matrix links software requirements to implementation modules and verification tests.

| Requirement | Description | Primary Implementation | Verification Evidence |
|---|---|---|---|
| FR-001 | Canonical CSV loading and normalization | `src/data/loading.py` | `tests/test_infra.py`, `tests/test_models_smoke.py` |
| FR-002 | Forecast orchestration and selection | `src/models/facade.py`, `src/models/compat_api.py` | `tests/test_models_smoke.py`, `tests/test_facade_import_smoke.py` |
| FR-003 | Normalized forecast artifact contract | `src/models/facade.py` | `tests/test_facade_import_smoke.py`, `tests/test_snapshot_outputs.py` |
| FR-004 | SVL structural export generation | `src/structural/svl_indicators.py`, `scripts/svl_export.py` | `tests/test_svl_indicators_unit.py`, `tests/test_part3_structural_exporters_acceptance.py` |
| FR-005 | TDA export with state handling | `src/structural/tda_indicators.py`, `scripts/tda_export.py` | `tests/test_tda_indicators_unit.py`, `tests/test_tda_module_contract.py`, `tests/test_tda_export_partial_degradation.py` |
| FR-006 | Follow-up draft/finalize lifecycle | `src/followup_ml/draft.py`, `scripts/followup_ml.py` | `tests/test_followup_ml_policy.py`, `tests/test_followup_ml_parity_tool.py` |
| FR-007 | VG materialization for ML/LLM paths | `src/followup_ml/vg_store.py`, `src/followup_ml/llm_vg_store.py` | `tests/test_followup_ml_vg_store.py`, `tests/test_followup_llm_vg_store.py` |
| FR-008 | Marker ingest with idempotency | `scripts/ann_markers_ingest.py` | `tests/test_followup_llm_vg_store.py` |
| FR-009 | Worker-based model isolation | `src/models/dynamix.py`, `scripts/workers/dynamix_worker.py`, `scripts/workers/pce_worker.py` | `tests/test_dynamix_integration.py`, `tests/test_models_smoke.py` |
| FR-010 | Artifact parity verification workflow | `scripts/followup_ml_parity.py`, `scripts/followup_ml_ci_parity_gate.py` | `tests/test_followup_ml_parity_tool.py` |
| FR-011 | Scope audit governance workflow | `src/followup_ml/scope_audit.py`, `scripts/followup_ml_scope_audit.py` | `tests/test_followup_ml_scope_audit.py` |
| FR-012 | Entrypoint startup/help operability | `app3G.py`, `scripts/*.py` | `tests/test_entrypoints_smoke.py`, `tests/test_app3g_smoke.py`, `tests/test_app3g_cli_help_smoke.py` |
| FR-013 | ANN feature store ingestion | `scripts/ann_feature_stores_ingest.py`, `src/ui/services/ann_ops.py` | `tests/test_ann_feature_stores_ingest.py`, `tests/test_streamlit_ann_ops.py` |
| FR-014 | ANN training and tuning workflows | `src/ann/*`, `scripts/ann_train.py`, `scripts/ann_tune.py` | `tests/test_ann_trainer.py`, `tests/test_ann_tune.py`, `tests/test_ann_training_dataset.py`, `tests/test_ann_training_config.py` |
| FR-015 | Review and streamlit operations workflow | `src/review/*`, `src/ui/review_streamlit.py`, `src/ui/services/*`, `scripts/review_streamlit.py` | `tests/test_review_repository.py`, `tests/test_review_exports.py`, `tests/test_review_streamlit_alignment.py`, `tests/test_streamlit_pipeline_runner.py`, `tests/test_streamlit_run_registry.py`, `tests/test_streamlit_pipeline_qa.py` |
| NFR-001 | Deterministic degradation behavior | optional-dep gating in `src/utils/compat.py`, TDA state handling | `tests/test_tda_module_contract.py`, `tests/test_tda_export_partial_degradation.py` |
| NFR-002 | Contract stability and compatibility | `compat/*` delegation layer, facade contracts | `tests/test_compat_capability_bridge.py`, `tests/test_facade_import_smoke.py` |
| NFR-003 | Compat thinness/import hygiene | `compat/*` + policy tests | `tests/test_compat_import_hygiene.py`, `tests/test_compat_thinness_shape.py` |
| NFR-004 | Snapshot and artifact reproducibility | `src/utils/calc_snapshots.py`, follow-up artifact writers | `tests/test_calc_snapshots.py`, `tests/test_snapshot_outputs.py` |
| NFR-005 | Path/bootstrap robustness | root shim and script bootstraps | `tests/test_paths_dotenv.py`, `tests/test_entrypoints_smoke.py` |

## Coverage Notes

- Matrix reflects current tests present in repository.
- Some requirements are validated by combined smoke + contract tests rather than one dedicated test file.
- CPI acceptance coverage is available through opt-in marker pathways (`--run-cpi`).
