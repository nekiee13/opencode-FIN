# Epic 5.2 Consolidated Rollback Reference

Date: 2026-03-22
Purpose: first-stop operator recovery guide for pilot runtime

## Fast triage order

1. Confirm workspace root: `C:\opencode-sandbox`
2. Confirm OpenCode health: `curl.exe -sS http://127.0.0.1:5096/global/health`
3. Confirm auth gate: `docker exec oc-fin-opencode opencode auth list`
4. Confirm model path: host and container `/v1/models` checks
5. Confirm MCP surface: `docker exec oc-fin-opencode opencode mcp list`

If any gate fails, use the matching rollback path below.

## A) Superpowers install/hook rollback

Use when:

- required skills are missing
- startup plugin load fails
- plugin pin drift is suspected

Rollback steps:

1. Back up active project config: `/workspace/.config/opencode/opencode.json`
2. Restore known-good plugin entry:
   - `superpowers@git+https://github.com/obra/superpowers.git#v5.0.5`
3. Restart runtime layer if needed
4. Verify with:
   - `docker exec oc-fin-opencode opencode debug skill`
   - required categories present

Detailed references:

- `docs/integration-pilot/epic-3-superpowers-recovery-snapshot.md`
- `docs/integration-pilot/epic-3-superpowers-rollback-drill.md`

## B) OAC payload/import rollback

Use when:

- OAC artifact completeness fails
- symlink targets break
- vendor payload regression is detected

Rollback steps:

1. Restore previous vendor snapshot directory (for example `vendor/OpenAgentsControl.backup-*`)
2. Re-validate required artifacts against selected version baseline
3. Re-run path-integrity checks for `.opencode/*` symlink targets
4. Re-run `python3 tools/hello-stack/check_stack.py`

Detailed references:

- `docs/integration-pilot/epic-2-oac-completeness-report.md`
- `docs/integration-pilot/epic-2-oac-path-integrity-check.md`

## C) Config regression rollback

Use when:

- startup/config parse errors occur
- MCP/plugin behavior drifts after config edits

Rollback steps:

1. Restore known-good project config at `/workspace/.config/opencode/opencode.json`
2. Validate JSON and UTF-8 encoding
3. Keep project/global key intent aligned with precedence policy
4. Re-run health + MCP checks

Detailed references:

- `docs/integration-pilot/epic-1-config-precedence.md`

## D) Workspace-level integration rollback

Use when:

- runtime appears stale or inconsistent
- container status is unstable
- gate checks fail after prior successful runs

Rollback steps:

1. Apply session reset sequence
2. Re-run deterministic opening gates in order
3. Re-check `check_stack.py`, MCP list, and skill visibility

Detailed references:

- `docs/integration-pilot/epic-1-session-reset-procedure.md`
- `docs/integration-pilot/epic-4-hello-stack-run.md`

## Exit condition

Rollback is considered complete when all conditions are true:

- health gate passes
- auth gate passes
- model gate passes
- MCP gate passes
- required Superpowers categories are visible
