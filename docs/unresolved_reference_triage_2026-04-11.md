# Unresolved Reference Triage (2026-04-11)

Scope: unresolved backticked file-path references in `docs/**/*.md` with extensions `md|mmd|json|py|csv|sqlite`.

## Outcome

- Initial unresolved references triaged: **67**
- Initial classification: **33** intentional runtime artifacts, **34** must-fix stale links
- Post-cleanup verification: **57** unresolved references, all classified as intentional runtime artifacts (**0** stale links remaining)

## Root Cause Summary

1. Runtime artifact references are intentionally pointing to generated outputs (for example `out/i_calc/...`, `trials.csv`, `best_config.json`) that are produced during runs and not tracked in git.
2. Stale references are mainly path-drift issues in historical pilot docs and OC docs (for example missing `.opencode/*` and vendor `.opencode` locations in current repo layout), plus one template placeholder reference.

## Intentional Runtime Artifacts (33)

| Reference | Occurrences | Source docs |
|---|---:|---|
| `best_config.json` | 2 | `docs/ann_tab_operator_guide.md`, `docs/followup_ml_runbook.md` |
| `best_summary.json` | 2 | `docs/ann_tab_operator_guide.md`, `docs/followup_ml_runbook.md` |
| `board.md` | 1 | `docs/followup_ml_runbook.md` |
| `dashboard/latest.md` | 1 | `docs/followup_ml_runbook.md` |
| `latest.md` | 1 | `docs/followup_ml_runbook.md` |
| `out/i_calc/LLM/LLM_VG_tables.sqlite` | 2 | `docs/fin/data/sql_json_schema.md`, `docs/followup_ml_runbook.md` |
| `out/i_calc/ML/ML_VG_tables.sqlite` | 2 | `docs/fin/data/sql_json_schema.md`, `docs/followup_ml_runbook.md` |
| `out/i_calc/Markers.sqlite` | 2 | `docs/fin/data/sql_json_schema.md`, `docs/followup_ml_runbook.md` |
| `out/i_calc/ann/feature_profiles/pruned_inputs.json` | 2 | `docs/ann_tab_operator_guide.md` |
| `out/i_calc/followup_ml/reports/parity_26-1-11.md` | 1 | `docs/followup_ml_runbook.md` |
| `out/i_calc/followup_ml/reports/scope_audit_YYYYMMDD.md` | 1 | `docs/followup_ml_runbook.md` |
| `out/i_calc/stores/ann_input_features.sqlite` | 4 | `docs/ann_tab_operator_guide.md`, `docs/fin/data/sql_json_schema.md`, `docs/followup_ml_runbook.md` |
| `out/i_calc/stores/ann_markers_store.sqlite` | 2 | `docs/ann_tab_operator_guide.md`, `docs/fin/data/sql_json_schema.md` |
| `round_context.json` | 1 | `docs/followup_ml_runbook.md` |
| `scores.csv` | 1 | `docs/followup_ml_runbook.md` |
| `state.json` | 1 | `docs/followup_ml_runbook.md` |
| `t0_day3_matrix.csv` | 1 | `docs/followup_ml_runbook.md` |
| `t0_day3_weighted_ensemble.csv` | 1 | `docs/followup_ml_runbook.md` |
| `t0_draft_metrics.csv` | 1 | `docs/followup_ml_runbook.md` |
| `t0_forecasts.csv` | 1 | `docs/followup_ml_runbook.md` |
| `trials.csv` | 2 | `docs/ann_tab_operator_guide.md`, `docs/followup_ml_runbook.md` |
| `weights.csv` | 1 | `docs/followup_ml_runbook.md` |

## Must-Fix Stale Links (34) - Cleanup Targets

| Reference | Occurrences | Source docs |
|---|---:|---|
| .opencode/INSTALL.md | 1 | `docs/integration-pilot/epic-3-superpowers-installation-log.md` |
| .opencode/config.json | 3 | `docs/integration-pilot/adr/0001-oac-version-selection.md`, `docs/integration-pilot/epic-2-oac-completeness-report.md`, `docs/integration-pilot/epic-2-oac-inventory-summary.md` |
| .opencode/opencode.json | 11 | `docs/integration-pilot/adr/0001-oac-version-selection.md`, `docs/integration-pilot/epic-2-oac-completeness-report.md`, `docs/integration-pilot/epic-2-oac-inventory-summary.md`, `docs/integration-pilot/epic-4-hello-stack-run.md`, `docs/oc/architecture/architecture.md`, `docs/oc/design/module_class_design.md`, `docs/oc/sws/software_specification.md` |
| NNNN-short-kebab-title.md | 1 | `docs/integration-pilot/adr/README.md` |
| check_stack.py | 5 | `docs/integration-pilot/epic-4-hello-stack-run.md`, `docs/integration-pilot/epic-5-rollback-reference.md`, `docs/integration-pilot/epic-6-comparison-report.md`, `docs/integration-pilot/epic-7-watchlist.md` |
| config.json | 1 | `docs/integration-pilot/epic-2-oac-completeness-report.md` |
| docs/oac_superpowers_hello_stack.md | 1 | `docs/integration-pilot/epic-0-benchmark-baseline.md` |
| evals/README.md | 4 | `docs/integration-pilot/adr/0001-oac-version-selection.md`, `docs/integration-pilot/epic-2-oac-completeness-report.md`, `docs/integration-pilot/epic-2-oac-inventory-summary.md` |
| opencode.json | 1 | `docs/integration-pilot/epic-3-superpowers-recovery-snapshot.md` |
| registry.json | 4 | `docs/integration-pilot/adr/0001-oac-version-selection.md`, `docs/integration-pilot/epic-2-oac-completeness-report.md`, `docs/integration-pilot/epic-2-oac-inventory-summary.md` |
| vendor/OpenAgentsControl/.opencode/README.md | 2 | `docs/integration-pilot/epic-0-baseline.md`, `docs/integration-pilot/epic-2-oac-inventory-summary.md` |

## Recommended Follow-up

1. Keep runtime-artifact references, but label them as generated outputs to avoid future false-positive link checks.
2. Rewrite stale references in `docs/integration-pilot/*` and `docs/oc/*` to either valid current paths or explicit historical text (non-link literals).
3. Keep ADR filename template text as a naming pattern, not as a link-like file reference.

## Cleanup Status

- Cleanup pass completed: stale references were converted to valid current paths or non-link historical literals in source docs.
