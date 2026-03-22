# Epic 7.3 Operator Quickstart and Troubleshooting

Date: 2026-03-22
Scope: validated pilot commands only

## Canonical startup path

Workspace and endpoint:

- workspace root: `C:\opencode-sandbox`
- OpenCode endpoint: `http://127.0.0.1:5096`
- container identity: `oc-fin-opencode`

Validated startup order:

1. GPU limit gate
2. llama.cpp start gate
3. llama listener gate
4. Docker engine gate
5. OpenCode container gate
6. OpenCode health gate
7. OAuth gate
8. container-to-host llama route gate
9. model registry gate
10. desktop open gate

## Basic diagnostic procedure

Run from PowerShell in canonical workspace:

```powershell
Set-Location C:\opencode-sandbox
docker info
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
curl.exe -sS http://127.0.0.1:5096/global/health
docker exec oc-fin-opencode opencode auth list
curl.exe -sS http://127.0.0.1:8080/v1/models
docker exec oc-fin-opencode curl -sS http://host.docker.internal:8080/v1/models
docker exec oc-fin-opencode opencode models
docker exec oc-fin-opencode opencode mcp list
docker exec oc-fin-opencode opencode debug skill
```

Pass expectation:

- health true
- OAuth present
- models include `openai/...`, `openai/...codex`, and `llamacpp/...`
- MCP includes `serena`, `jcodemunch`, `jdocmunch`
- required Superpowers categories visible

## Rollback references

- first-stop rollback guide: `docs/integration-pilot/epic-5-rollback-reference.md`
- session reset procedure: `docs/integration-pilot/epic-1-session-reset-procedure.md`
- guardrails page: `docs/integration-pilot/epic-5-guardrails.md`

## Known unsupported paths

- direct host use of port `4096`
- non-canonical workspace roots for pilot validation
- startup orders that begin OpenCode before llama.cpp readiness
- compose/runtime identity drift away from `oc_fin` and `oc-fin-opencode`
