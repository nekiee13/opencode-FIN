# Epic 5.1 Focused Failure Register

Date: 2026-03-22
Scope: boundary failures only, pilot-focused

## Seed from hello-stack (Epic 4.5)

- Real failures observed: none
- Boundary-localized failure entries seeded from real run: none

## Top likely boundary failures (maximum set: 5)

### FR-01 - Wrong workspace boundary

- Symptom: expected config, MCP surface, or file paths do not match pilot baseline
- Likely cause: execution started outside canonical workspace root
- Detection clue: `Get-Location` is not `C:\opencode-sandbox`, or active config path resolves outside `/workspace/.config/opencode/`
- Recovery path: switch to canonical workspace, rerun diagnostic bundle, then rerun affected workflow stage

### FR-02 - Config precedence/drift boundary

- Symptom: plugin or MCP behavior changes across fresh starts with no intended change
- Likely cause: project and global config keys drifted or became invalid
- Detection clue: project file and global file disagree on critical keys, or JSON parse/startup errors appear
- Recovery path: restore known-good project config, validate JSON encoding/shape, then rerun health and MCP checks

### FR-03 - Stale runtime/process boundary

- Symptom: health checks fail intermittently or container status is `Restarting/Exited/Dead`
- Likely cause: stale container/process state after prior run
- Detection clue: `docker ps -a` shows unstable container status, auth/model checks fail after health timeout
- Recovery path: apply session reset procedure, then repeat health -> auth -> model checks in order

### FR-04 - Superpowers preflight boundary

- Symptom: required skills are missing or startup plugin load fails
- Likely cause: invalid plugin reference, config regression, or install drift
- Detection clue: `opencode debug skill` misses required categories, or startup log contains plugin install/load errors
- Recovery path: restore valid plugin pin (`v5.0.5`), rerun startup and skill checks, then proceed with preflight

### FR-05 - Retrieval index drift boundary

- Symptom: retrieval stage cannot find indexed repo or expected sections/symbols
- Likely cause: stale or missing jCodeMunch/jDocMunch index for active snapshot
- Detection clue: search returns `Repo not found` or empty results for known sections/symbols
- Recovery path: re-index affected repo/folder, rerun retrieval query, then continue workflow

## Drill note (Epic 5.4 linkage)

- Scenario exercised: `FR-05` retrieval index drift
- Result: completed successfully
- Evidence:
  - `jdocmunch_search_sections` succeeded before index deletion
  - `jdocmunch_delete_index` produced `Repo not found` state on next query
  - `jdocmunch_index_local` restored index
  - retrieval query succeeded after re-index
