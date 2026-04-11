# FIN Documentation Set

Last reviewed: 2026-04-11
Source commit: `055c7bc`

This folder contains the authoritative FIN runtime documentation for the current project state.

## Scope

Included:

- `src/`, `compat/`, `scripts/`, `tests/`, `data/`, `config/`
- FIN runtime behavior, interfaces, schemas, and operational constraints

Excluded:

- OC runtime and OC pilot internals (`docs/oc/`, `docs/integration-pilot/`)
- Vendor internals except direct FIN integration boundaries

## Current Runtime Surfaces Covered

- Forecast core (`src/models/*`) and facade contract (`ForecastArtifact`)
- Follow-up ML and VG/LLM/marker stores (`src/followup_ml/*`)
- Structural exports (SVL/TDA)
- ANN pipeline and ingestion/training/tuning surfaces (`src/ann/*`, `scripts/ann_*`)
- Review and Streamlit operations (`src/review/*`, `src/ui/review_streamlit.py`, `src/ui/services/*`)

## Deliverables

- Python architecture: `docs/fin/architecture/python_architecture.md`
- Module/class design: `docs/fin/design/module_class_design.md`
- Pydantic model specification: `docs/fin/design/pydantic_model_spec.md`
- End-to-end pipeline diagrams: `docs/fin/diagrams/end_to_end_pipeline.md`
- UML class diagram: `docs/fin/diagrams/uml_class_diagram.md`
- UML sequence diagrams: `docs/fin/diagrams/uml_sequence_diagrams.md`
- SQL/JSON schemas: `docs/fin/data/sql_json_schema.md`
- Software specification (SwS): `docs/fin/spec/software_specification.md`
- Requirements traceability: `docs/fin/spec/requirements_traceability.md`
- FIN docs backlog: `docs/fin/backlog/github_issues_documentation_plan.md`

## Conventions

- Mermaid is used for architecture/UML/ER diagrams.
- Paths and contracts map to the current repository state.
- Requirement IDs in SwS are mapped in `docs/fin/spec/requirements_traceability.md`.
- Operational runbook companions in root docs:
  - `docs/followup_ml_runbook.md`
  - `docs/ann_tab_operator_guide.md`
