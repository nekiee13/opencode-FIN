# Epic 7.1 Bounded Single-Operator Pilot Report

Date: 2026-03-22
Scope: fixed, single-operator pilot only

## Pilot execution matrix

Minimum requirement target:

- at least 3 workflow executions
- at least 2 distinct task categories
- at least 3 separate working sessions

Observed execution set:

1. `WX-01` Deterministic runtime bring-up and gate validation
   - category: runtime bring-up/diagnostics
   - session: `S1`
   - evidence: `docs/integration-pilot/epic-0-baseline.md`, `docs/integration-pilot/epic-1-runtime-topology.md`
   - result: pass
2. `WX-02` Superpowers install/verification and rollback validation
   - category: behavioral preflight + recovery
   - session: `S2`
   - evidence: `docs/integration-pilot/epic-3-superpowers-installation-log.md`, `docs/integration-pilot/epic-3-superpowers-verification-log.md`, `docs/integration-pilot/epic-3-superpowers-rollback-drill.md`
   - result: pass
3. `WX-03` Hello-stack end-to-end retrieval -> preflight -> approval -> edit -> test/result
   - category: integrated workflow execution
   - session: `S3`
   - evidence: `docs/integration-pilot/epic-4-hello-stack-run.md`
   - result: pass

Additional executed scenario:

- `WX-04` failure-handling drill for index drift (`FR-05`)
  - category: failure handling/recovery
  - session: `S3`
  - evidence: `docs/integration-pilot/epic-5-failure-register.md`
  - result: pass

Requirement judgment:

- workflow count: satisfied (`>=3`)
- category count: satisfied (`>=2`)
- session count: satisfied (`>=3`)
- calendar-day spread: not met as hard separation; treated as acceptable because this constraint is soft in plan language

## Friction observed

- Active config path ambiguity (`.opencode` versus `.config/opencode`) caused initial write-target failures.
- PowerShell edition differences caused `utf8NoBOM` encoding command mismatch.
- Regex matching in `Select-String` produced false negatives for plugin-load checks.
- Build shell lacked `docker` binary, limiting direct host/container benchmark parity checks in that shell.

## Workarounds used

- Active config path was discovered directly inside runtime container before edits.
- PowerShell 5.1 fallback write method was used for UTF-8 without BOM.
- `Select-String -SimpleMatch` replaced regex matching for literal plugin path checks.
- Runtime/auth/model outcome checks were captured through OpenCode CLI when host endpoint checks were unavailable in build shell.

## Unresolved blockers

- `pytest` is still missing in the evaluated build shell (`No module named pytest`).
- Direct endpoint comparability for `B1` depends on canonical host shell where `127.0.0.1:5096` and `127.0.0.1:8080` are reachable.

## Pilot conclusion for Task 7.1

- Bounded pilot scope requirements were met for execution count, category breadth, and session count.
- Evidence is sufficient to support Task 7.2 decision output.
