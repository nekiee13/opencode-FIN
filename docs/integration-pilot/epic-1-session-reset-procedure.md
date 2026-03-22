# Epic 1.2 Session Reset Procedure

Date: 2026-03-22

## Purpose

This procedure creates a clean enough start state for pilot diagnostics.

## Fresh-start definition (pilot)

A session is treated as fresh when all conditions are true:

- Docker engine responds to `docker info`.
- `oc-fin-opencode` is not in stale or restarting state.
- llama.cpp listener status is known (`ready` or `not running`).
- Workspace root is `C:\opencode-sandbox`.

## Reset steps

1. Set workspace: `Set-Location C:\opencode-sandbox`
2. Check engine: `docker info`
3. Stop stale OpenCode container if present: `docker rm -f oc-fin-opencode` (only when status is `Exited`, `Restarting`, or `Dead`)
4. Verify llama listener state: `curl.exe -sS http://127.0.0.1:8080/v1/models`
5. Start OpenCode layer: `docker compose -f docker-compose.opencode.yml up -d`
6. Confirm health: `curl.exe -sS http://127.0.0.1:5096/global/health`

## Stale-process checks

- `docker ps -a --format "table {{.Names}}\t{{.Status}}"`
- `docker ps --format "table {{.Names}}\t{{.Ports}}"`
- `docker exec oc-fin-opencode opencode auth list`

## Ambiguity reduction notes

- `503 Loading model` from llama endpoint is treated as warm-up, not a hard failure.
- Missing `OpenAI oauth` is treated as auth state failure.
- Port `5096` is always used for host checks.

## Reproducibility level

- Procedure target is practical reproducibility for troubleshooting.
- Byte-for-byte replay is not required by pilot policy.
