# Governance Transition

Last reviewed: 2026-04-11

## Current Governance Mode

- Workflow mode: trunk-only on `main`
- Active runtime scope: `oc-fin-opencode`
- Paused runtime scope: `oc-fin`

## Operating Rules

1. Develop directly on `main` unless an explicit exception is approved.
2. Keep runtime and docs aligned in the same change set when interfaces/workflows change.
3. Treat `docs/README.md` as the authoritative docs entrypoint.

## Sync Procedure

Daily sync commands:

```bash
git fetch origin --prune
git rev-parse HEAD
git rev-parse origin/main
git pull --ff-only origin main
git push origin main
```

## Divergence Recovery

Use only when local commits are intentionally discarded:

```bash
git reset --hard origin/main
```

## Documentation Governance

- FIN runtime docs owner: FIN maintainers (`docs/fin/*`)
- OC docs owner: OC maintainers (`docs/oc/*`)
- Integration pilot owner: pilot maintainers (`docs/integration-pilot/*`)
- Refactor invariants owner: core maintainers (`docs/refactor/*`)

File-level freshness status is tracked in `docs/documentation_freshness_ledger.md`.
