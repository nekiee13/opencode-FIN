# OpenCode Runtime Safe Open/Close (Canonical)

Last reviewed: 2026-04-27
Status: Current operational guidance

This runbook defines canonical FIN runtime startup and shutdown entrypoints.

## Canonical Host Port Contract

- FIN runtime: `127.0.0.1:5096->4096`

## Canonical Entry Points

- FIN open: `scripts/runtime/safe-open-fin.ps1`
- FIN close: `scripts/runtime/safe-close-fin.ps1`
- Shared helper: `scripts/runtime/_runtime_common.ps1`

## Gate Model

Each script prints deterministic gate lines:

`GATE=<name> RESULT=<code> MESSAGE=<details>`

Expected result codes:

- `PASS`
- `SKIP_ABSENT`
- `FAIL_PORT_IN_USE`
- `FAIL_DOCKER`
- `FAIL_HEALTH`

## Operational Notes

- `safe-open-fin.ps1` validates Docker readiness, compose startup, FIN health, auth, and model visibility.
- `safe-close-fin.ps1` stops compose runtime, removes FIN container idempotently, and confirms host port clear.
- Loopback host must remain `127.0.0.1`.
