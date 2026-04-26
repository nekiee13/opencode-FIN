# Repository Documentation Index

Last reviewed: 2026-04-11
Source commit: `055c7bc`

This index is the primary entry point for all documentation in this repository.

## Documentation Sets

| Set | Path | Purpose | Status |
|---|---|---|---|
| FIN runtime | `docs/fin/` | Forecasting and scenario engine architecture, contracts, and SwS | Current |
| Operational runbooks | `docs/*.md` (root) | Follow-up ML operations, ANN operator flow, governance notes | Current |
| OpenCode (OC) | `docs/oc/` | OC-specific architecture, entities, diagrams, and SwS | Current |
| Integration pilot evidence | `docs/integration-pilot/` | Time-bounded pilot execution evidence and ADRs | Historical evidence |
| Refactor governance | `docs/refactor/` | Phase-1 invariants and architectural decisions | Current |

## Start Here

- FIN runtime docs: `docs/fin/README.md`
- OC docs: `docs/oc/README.md`
- Integration pilot status and usage: `docs/integration-pilot/README.md`
- Phase-1 invariants: `docs/refactor/phase1_rules.md`
- Governance transition and trunk operations: `docs/governance-transition.md`

## Freshness and Ownership

- Full file-level inventory and actions: `docs/documentation_freshness_ledger.md`
- Generated OC artifacts are snapshots and must be refreshed via OC docs build flow.
- Integration pilot files remain retained as evidence and should not be treated as default runtime instructions unless explicitly marked current.

## Maintenance Policy

- Review cadence: at least once per sprint, or immediately after contract/entrypoint changes.
- Required metadata updates on meaningful doc changes:
  - `Last reviewed`
  - source commit/hash reference where applicable
  - status classification (`Current`, `Historical evidence`, `Generated snapshot`)
- PR checklist requirement: update docs whenever interfaces, schemas, runbooks, or operator workflows change.

- Canonical FIN runtime open/close runbook: `docs/opencode-runtime-safe-open-close.md`
