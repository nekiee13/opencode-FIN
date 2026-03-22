# Epic 5.3 Practical Pilot Guardrails

Date: 2026-03-22
Scope: common drift/failure conditions only

## Guardrail 1 - Config drift

- Trigger: behavior changes after config edits or restarts
- Check:
  - `/workspace/.config/opencode/opencode.json`
  - `/home/opencode/.config/opencode/opencode.json`
- Action: restore known-good project config, validate JSON + encoding, rerun health and MCP gates

## Guardrail 2 - Hook/plugin drift

- Trigger: required skills disappear or plugin load errors appear
- Check:
  - plugin pin in project config
  - `opencode debug skill` category presence
- Action: reapply pinned plugin reference and re-verify skills

## Guardrail 3 - Stale workspace/runtime

- Trigger: intermittent failures, stale container states, inconsistent startup
- Check:
  - `docker ps -a --format "table {{.Names}}\t{{.Status}}"`
  - health/auth/model gates in deterministic order
- Action: run session reset procedure, then rerun opening sequence gates

## Guardrail 4 - Index drift

- Trigger: retrieval stage returns missing repo/empty known queries
- Check:
  - jCodeMunch/jDocMunch repo list and query results
- Action: re-index affected folder/repo, rerun retrieval query before planning stage

## Guardrail 5 - OAC payload regression

- Trigger: path integrity or required artifact checks fail
- Check:
  - selected-version completeness list
  - `.opencode` symlink target validity
- Action: restore known-good vendor snapshot, rerun completeness + path-integrity checks
