# FIN Documentation Set

This folder contains the generated documentation baseline for the current `opencode-FIN` project state.

Scope lock:
- Included: `src/`, `compat/`, `scripts/`, `tests/`, `data/`, `config/`, and FIN runtime docs.
- Excluded: agent framework/orchestration assets (`.opencode`, non-FIN runtime assets), and vendor internals except where FIN directly integrates with them.

## Deliverables

- Python Architecture Diagram: `docs/fin/architecture/python_architecture.md`
- Python Module/Class Design: `docs/fin/design/module_class_design.md`
- Pydantic Model Specification (from dataclass entities): `docs/fin/design/pydantic_model_spec.md`
- End-to-End Pipeline Diagram: `docs/fin/diagrams/end_to_end_pipeline.md`
- UML Class Relationship Diagram: `docs/fin/diagrams/uml_class_diagram.md`
- UML Sequence Diagrams: `docs/fin/diagrams/uml_sequence_diagrams.md`
- SQL and JSON Data Schema: `docs/fin/data/sql_json_schema.md`
- Software Specification (SwS): `docs/fin/spec/software_specification.md`
- Requirements Traceability Matrix: `docs/fin/spec/requirements_traceability.md`
- GitHub-Issues Style Doc Backlog: `docs/fin/backlog/github_issues_documentation_plan.md`

## Documentation Conventions

- Mermaid is used for all architecture/UML/ER diagrams.
- Paths and contracts reflect the current code in this repository.
- On parse errors while auto-inventorying files (for example, invalid payload shape), the file is skipped and documented in the backlog validation notes.
