# Epic 1.1 Canonical Runtime Topology

Date: 2026-03-22

## Canonical startup path (pilot)

- Step order is fixed by policy: GPU limit -> llama.cpp -> llama listener check -> Docker engine check -> `oc-fin` -> `oc-fin-opencode` -> OpenCode health -> OAuth -> container-to-host llama route -> model registry.
- Canonical workspace root: `C:\opencode-sandbox`.
- Canonical OpenCode host endpoint: `http://127.0.0.1:5096`.
- Container internal OpenCode port: `4096/tcp` (not used as host entry).
- Canonical model listener: `http://127.0.0.1:8080/v1/models`.

## Canonical object map

- Workspace key: `fin`
- Compose project: `oc_fin`
- Workspace container: `oc-fin`
- OpenCode container: `oc-fin-opencode`
- Required host port map: `127.0.0.1:5096->4096/tcp`

## Canonical config roots

- Project-local root (pilot workspace): `C:\opencode-sandbox\.opencode\`
- Project-local config file: `C:\opencode-sandbox\.opencode\opencode.json`
- Runtime-global config root (container/runtime user): `/home/opencode/.config/opencode/`
- Runtime-global config file: `/home/opencode/.config/opencode/opencode.json`

## Non-canonical paths (unsupported for pilot validation)

- Direct host access to port `4096`.
- Startup sequences that start OpenCode before llama.cpp readiness.
- Launching from workspace roots other than `C:\opencode-sandbox`.
- Compose project names that drift from `oc_fin`.
- Mixed runtime identities where `oc-fin-opencode` is replaced by alternate container names.

## Consistency evidence

- Run 1 (2026-03-22): pass for health, OAuth, model routing, and model registry gates.
- Run 2 (2026-03-22): pass for workspace, engine, container mapping, health, OAuth, host llama route, container llama route, model registry, and MCP connectivity gates.
- Run 3 (pre-2026-03-22): pass reported from multiple prior safe shutdown/startup cycles under the same canonical topology.

Pilot status:

- Canonical topology is defined.
- Three-run fresh-start consistency check is treated as satisfied for pilot diagnostics, with Run 3 supported by operator-reported prior cycle evidence.
