# SOFTWARE SPECIFICATION (SwS) - OpenCode Stack

## 1. Document Scope

This specification defines the current OpenCode stack behavior inside this repository.

In scope:

- OpenCode runtime configuration and plugin loading
- OAC registry and component model used by runtime
- Superpowers behavior injection and preflight posture
- Serena and Munch MCP integration path
- OAC evaluation and workflow evidence handling

Out of scope:

- Forecasting and finance logic in `src/`, `compat/`, `scripts/`

## 2. Glossary

- OC: OpenCode runtime in this repository.
- OAC: OpenAgentsControl payload and control-plane model.
- MCP: Model Context Protocol server integration endpoint.
- Retrieval evidence: source-traceable code and docs references.
- Stage artifact: file-backed record proving a workflow stage result.
- Invalid-file skip: policy to skip files when invalid payload errors are detected.

## 3. System Context

The OC system operates as a layered stack:

1. Runtime Layer (OpenCode process + runtime config)
2. Control Layer (OAC registry + agent graph + approvals)
3. Retrieval Layer (jCodeMunch + jDocMunch)
4. Edit Layer (Serena)
5. Evaluation Layer (OAC eval framework + pilot evidence)

Reference architecture: `docs/oc/architecture/architecture.md`

## 4. Functional Requirements

| ID | Requirement |
| --- | --- |
| FR-OC-001 | Runtime shall load plugin and MCP configuration from `.opencode/opencode.json`. |
| FR-OC-002 | OAC registry shall define component graph for agents, subagents, commands, tools, skills, and contexts. |
| FR-OC-003 | Retrieval stage shall collect code context from jCodeMunch before edit stage starts. |
| FR-OC-004 | Retrieval stage shall collect docs context from jDocMunch before edit stage starts. |
| FR-OC-005 | Preflight shall verify required Superpowers skill posture before approval request. |
| FR-OC-006 | Approval gate decision shall be required before edit execution. |
| FR-OC-007 | Semantic edits shall be performed through Serena as the preferred path. |
| FR-OC-008 | Verification command output shall be attached to final stage artifact. |
| FR-OC-009 | Workflow failures shall be localized to stage boundary and reported with evidence. |
| FR-OC-010 | Documentation build shall generate OC inventory and entity indexes from in-scope files only. |
| FR-OC-011 | Invalid file payload pattern (`{"type":"error" ... "type":"invalid...`) shall trigger skip behavior. |
| FR-OC-012 | Skipped invalid files shall be recorded in `docs/oc/generated/skipped_invalid_files.json`. |

## 5. Non-Functional Requirements

| ID | Requirement |
| --- | --- |
| NFR-OC-001 | Configuration and control authority shall be deterministic across repeated runs under same topology. |
| NFR-OC-002 | Stage transitions shall be evidence-driven, not narrative-only. |
| NFR-OC-003 | Stack behavior shall remain auditable through file-backed artifacts. |
| NFR-OC-004 | Retrieval and entity generation steps shall continue after per-file invalid errors by skipping failing files. |
| NFR-OC-005 | Generated documentation artifacts shall be reproducible via a single command. |

## 6. External Interfaces

### 6.1 Runtime Configuration Interface

- Path: `.opencode/opencode.json`
- Inputs: plugin array, MCP server command definitions
- Outputs: active runtime plugin and MCP behavior

### 6.2 OAC Registry Interface

- Path: `vendor/OpenAgentsControl/registry.json`
- Inputs: component metadata and dependencies
- Outputs: control-plane component graph used by runtime tooling

### 6.3 Retrieval Interfaces

- jCodeMunch: symbol and source retrieval operations
- jDocMunch: section-level documentation retrieval operations

### 6.4 Edit Interface

- Serena MCP semantic edit operations

### 6.5 Evaluation Interface

- OAC eval framework classes under `vendor/OpenAgentsControl/evals/framework/src/`

## 7. Data Model

### 7.1 Core Runtime Entities

- `CheckResult` dataclass: stack check status object
- `Ability`: executable ability definition
- `Step` and `ScriptStep`: executable step units
- `AbilityExecution` and `StepResult`: runtime execution state and outcome records

### 7.2 Entity Catalog Artifacts

- Human-readable catalog: `docs/oc/entities/entity_catalog.md`
- Dataclass mirrors: `docs/oc/entities/entity_dataclasses.py`
- Machine-readable index: `docs/oc/generated/oc_class_index.json`

## 8. Workflow Definition

Reference diagram: `docs/oc/pipeline/end_to_end_pipeline.md`

Pipeline stages:

1. Retrieval (code + docs evidence)
2. Planning and preflight (skills + target + verification command)
3. Approval (gate decision)
4. Edit (Serena execution)
5. Test/result (verification command + final artifact)

## 9. Error Handling and Recovery

### 9.1 Runtime Workflow Errors

- Preflight failure: blocks approval request
- Gate denial: blocks edit
- Edit failure: blocks test/result
- Test failure: blocks completion

### 9.2 Documentation Generation Errors

- On invalid payload pattern or invalid parse error, file is skipped.
- Skip event is written to `docs/oc/generated/skipped_invalid_files.json`.
- Build continues for remaining files.

## 10. Security and Governance

- Approval gate authority remains with OAC control model.
- Behavioral skills do not override gate decisions.
- Retrieval and edit claims require source evidence.
- Symlink path integrity remains required for active `.opencode` runtime wiring.

## 11. Observability

Primary observability artifacts:

- `docs/integration-pilot/epic-4-hello-stack-run.md`
- `docs/integration-pilot/epic-3-superpowers-verification-log.md`
- `docs/integration-pilot/epic-2-oac-path-integrity-check.md`
- `docs/oc/generated/oc_inventory.json`
- `docs/oc/generated/skipped_invalid_files.json`

## 12. Constraints

- OC-only documentation scope is enforced.
- FIN modeling code is excluded.
- Vendored OAC payload is treated as source of truth for OAC internals in this repository.
- Generated entity model may use `Any` for TypeScript-to-dataclass type portability.

## 13. Requirement Traceability

| Requirement ID | Source Evidence |
| --- | --- |
| FR-OC-001 | `.opencode/opencode.json` |
| FR-OC-002 | `vendor/OpenAgentsControl/registry.json` |
| FR-OC-003 | `docs/integration-pilot/epic-4-operator-policy.md` |
| FR-OC-004 | `docs/integration-pilot/epic-4-operator-policy.md` |
| FR-OC-005 | `docs/integration-pilot/epic-3-superpowers-verification-log.md` |
| FR-OC-006 | `docs/integration-pilot/adr/0003-control-plane-authority-hierarchy.md` |
| FR-OC-007 | `docs/integration-pilot/epic-4-operator-policy.md` |
| FR-OC-008 | `docs/integration-pilot/epic-4-workflow-artifact-spec.md` |
| FR-OC-009 | `docs/integration-pilot/epic-5-failure-register.md` |
| FR-OC-010 | `tools/oc_docs/build_oc_docs.py` |
| FR-OC-011 | `tools/oc_docs/build_oc_docs.py` |
| FR-OC-012 | `docs/oc/generated/skipped_invalid_files.json` |
| NFR-OC-001 | `docs/integration-pilot/epic-1-runtime-topology.md` |
| NFR-OC-002 | `docs/integration-pilot/epic-4-workflow-artifact-spec.md` |
| NFR-OC-003 | `docs/integration-pilot/epic-7-pilot-report.md` |
| NFR-OC-004 | `tools/oc_docs/build_oc_docs.py` |
| NFR-OC-005 | `tools/oc_docs/build_oc_docs.py` |
