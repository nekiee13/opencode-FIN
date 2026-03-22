# Epic 1.4 Diagnostic Bundle Procedure

Date: 2026-03-22
Target run time: under 5 minutes

## Command bundle

Run in PowerShell from `C:\opencode-sandbox`.

1. Workspace and config source

```powershell
Get-Location
Test-Path .\.opencode\opencode.json
```

2. Engine and container state

```powershell
docker info
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

3. OpenCode runtime health and auth gate

```powershell
curl.exe -sS http://127.0.0.1:5096/global/health
docker exec oc-fin-opencode opencode auth list
```

4. Model path checks

```powershell
curl.exe -sS http://127.0.0.1:8080/v1/models
docker exec oc-fin-opencode curl -sS http://host.docker.internal:8080/v1/models
docker exec oc-fin-opencode opencode models
```

## Classification map

- Wrong workspace
  - Clue: `Get-Location` is not `C:\opencode-sandbox` or `.opencode\opencode.json` is missing.
  - Primary recovery: switch workspace root and rerun bundle.

- Config issue
  - Clue: health endpoint fails while container is running, or expected MCP/model entries are missing.
  - Primary recovery: validate project and global config JSON, then fresh restart.

- Stale session/process
  - Clue: container in `Restarting/Exited/Dead`, or stale duplicate containers exist.
  - Primary recovery: apply session reset procedure, then rerun health/auth checks.

- Runtime conflict
  - Clue: llama host listener passes but container cannot reach `host.docker.internal:8080`, or host port binding conflicts appear.
  - Primary recovery: inspect container network and port mappings, then restart OpenCode container layer.

## Output handling

- Save command outputs as a single troubleshooting record.
- Root-cause class must be assigned before deeper debugging begins.
