# FIN Documentation Backlog (GitHub-Issues Style)

This backlog is structured as epics with tasks and acceptance criteria.

## EPIC FIN-DOC-00 - Scope Lock and Inventory

Tasks:
- [ ] FIN-DOC-001 Define FIN-only documentation boundary and exclusions.
- [ ] FIN-DOC-002 Build module/entity inventory for `src`, `compat`, `scripts`, and persistence contracts.
- [ ] FIN-DOC-003 Publish documentation IA and cross-link map.
- [ ] FIN-DOC-004 Enforce skip-on-invalid-file parsing rule and log skipped items.

Acceptance Criteria:
- [ ] Included and excluded paths are explicit.
- [ ] Inventory covers all active FIN runtime modules and entity contracts.
- [ ] Docs index links every required deliverable.
- [ ] Any skipped files are logged with reason.

## EPIC FIN-DOC-01 - Python Architecture Diagram

Tasks:
- [ ] FIN-DOC-101 Create high-level architecture Mermaid diagram.
- [ ] FIN-DOC-102 Mark canonical vs compat ownership boundaries.
- [ ] FIN-DOC-103 Show worker integration and IPC boundaries.
- [ ] FIN-DOC-104 Show storage/output subsystem boundaries.

Acceptance Criteria:
- [ ] Diagram renders in GitHub.
- [ ] All major runtime components are represented and mapped to actual modules.
- [ ] Ownership boundaries are visible and consistent with Phase-1 rules.

## EPIC FIN-DOC-02 - Module/Class Design

Tasks:
- [ ] FIN-DOC-201 Document folder structure and responsibilities.
- [ ] FIN-DOC-202 Document module-level API responsibilities.
- [ ] FIN-DOC-203 Publish class/entity catalog.
- [ ] FIN-DOC-204 Document import/dependency relationships.

Acceptance Criteria:
- [ ] Every active FIN module is covered.
- [ ] Class/entity catalog includes dataclass and enum contracts.
- [ ] Responsibility definitions match current implementation.

## EPIC FIN-DOC-03 - Pydantic Model Specification

Tasks:
- [ ] FIN-DOC-301 Map dataclass entities to Pydantic model definitions.
- [ ] FIN-DOC-302 Define field constraints and optionality.
- [ ] FIN-DOC-303 Provide schema examples for core payloads.
- [ ] FIN-DOC-304 Add compatibility notes for worker and storage payloads.

Acceptance Criteria:
- [ ] All identified dataclass entities have a Pydantic equivalent spec.
- [ ] Required vs optional fields are explicit.
- [ ] Example payloads cover forecast, worker, and follow-up flows.

## EPIC FIN-DOC-04 - End-to-End Pipeline Diagrams

Tasks:
- [ ] FIN-DOC-401 Forecasting pipeline diagram.
- [ ] FIN-DOC-402 Structural export pipeline diagram (SVL/TDA).
- [ ] FIN-DOC-403 Follow-up ML/VG pipeline diagram.
- [ ] FIN-DOC-404 Failure/degradation branches in each pipeline.

Acceptance Criteria:
- [ ] Diagrams render in GitHub.
- [ ] Inputs, processing stages, and outputs are complete and labeled.
- [ ] Degradation behavior matches current code paths.

## EPIC FIN-DOC-05 - UML Class Relationship Diagram

Tasks:
- [ ] FIN-DOC-501 Model result and facade contract relationships.
- [ ] FIN-DOC-502 Structural context and follow-up entity relationships.
- [ ] FIN-DOC-503 Annotate composition/association semantics.

Acceptance Criteria:
- [ ] Mermaid `classDiagram` renders successfully.
- [ ] Core entities and relationships reflect implemented usage.

## EPIC FIN-DOC-06 - UML Sequence Diagrams

Tasks:
- [ ] FIN-DOC-601 app3G analysis sequence.
- [ ] FIN-DOC-602 DynaMix worker sequence.
- [ ] FIN-DOC-603 Follow-up draft/finalize sequence.
- [ ] FIN-DOC-604 TDA export degradation sequence.

Acceptance Criteria:
- [ ] Mermaid `sequenceDiagram` blocks render and include success/failure branches.
- [ ] Participant boundaries are mapped to real modules/scripts.

## EPIC FIN-DOC-07 - SQL and JSON Schemas

Tasks:
- [ ] FIN-DOC-701 Document sqlite schemas (`VG`, `LLM_VG`, `Markers`, `ANN ingest`).
- [ ] FIN-DOC-702 Add Mermaid ERD(s).
- [ ] FIN-DOC-703 Document JSON schemas (`dynamix`, `pce_worker`, `round_context`, `parity_manifest`).
- [ ] FIN-DOC-704 Define schema versioning notes.

Acceptance Criteria:
- [ ] SQL table specs align with code DDL definitions.
- [ ] JSON schema required fields and error envelopes are explicit.
- [ ] Mermaid ERD renders and reflects key relationships.

## EPIC FIN-DOC-08 - Software Specification (SwS)

Tasks:
- [ ] FIN-DOC-801 Write complete SwS (scope, architecture, interfaces, behavior).
- [ ] FIN-DOC-802 Define functional and non-functional requirements.
- [ ] FIN-DOC-803 Link requirements to test and implementation evidence.
- [ ] FIN-DOC-804 Add operational and rollout constraints.

Acceptance Criteria:
- [ ] SwS is complete and self-contained.
- [ ] Requirement traceability is documented.
- [ ] Operational expectations are explicit and actionable.

## EPIC FIN-DOC-09 - Validation and Publication Gate

Tasks:
- [ ] FIN-DOC-901 Mermaid render validation.
- [ ] FIN-DOC-902 Link/reference integrity checks.
- [ ] FIN-DOC-903 Consistency check against current code.
- [ ] FIN-DOC-904 Documentation completion report.

Acceptance Criteria:
- [ ] All diagrams render.
- [ ] No broken internal links.
- [ ] Coverage is complete for requested documentation scope.
