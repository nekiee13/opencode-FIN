# Epic 1.3 Config Precedence and Windows-Safe Encoding

Date: 2026-03-22

## Scope

This note defines practical precedence for pilot diagnostics and startup behavior.

## Config placement rules

- Global config (`/home/opencode/.config/opencode/opencode.json`) stores broad defaults.
- Project config (`/workspace/.config/opencode/opencode.json`) stores pilot workspace choices in the running container.
- Host mirror path for project config is expected at `C:\opencode-sandbox\.config\opencode\opencode.json`.
- Credentials remain in runtime auth store (`~/.local/share/opencode/auth.json` inside runtime user context).

## Precedence policy

- Global only present: global settings are used.
- Project only present: project settings are used.
- Both present with non-overlapping keys: both are applied.
- Both present with conflicting keys: project value is treated as authoritative for pilot behavior.
- Invalid file (global or project): startup is treated as failed until valid JSON is restored.

## Practical consistency checks

- Run from canonical workspace: `C:\opencode-sandbox`.
- Confirm active MCP surface after fresh start: `opencode mcp list` (or `docker exec oc-fin-opencode opencode mcp list`).
- If MCP surface changes between fresh starts, config drift is suspected first.

Observed precedence evidence (2026-03-22):

- Project config showed only `serena` under `mcp`.
- Runtime `opencode mcp list` still returned `serena`, `jcodemunch`, and `jdocmunch`.
- Behavior indicates effective merge between project and global scope in this runtime.

## Windows-safe encoding guidance

- Use UTF-8 without BOM for all JSON/YAML config files.
- Avoid mixed encodings across global and project config files.
- CRLF line endings are acceptable when file parsing remains valid.

PowerShell check for BOM (first three bytes):

```powershell
$path = "C:\opencode-sandbox\.config\opencode\opencode.json"
[byte[]]$head = Get-Content -Path $path -Encoding Byte -TotalCount 3
$head
```

Interpretation:

- `239 187 191` means UTF-8 BOM is present.
- Any other leading bytes require standard JSON validity check.

PowerShell 7 write without BOM:

```powershell
Set-Content -Path "C:\opencode-sandbox\.config\opencode\opencode.json" -Value $json -Encoding utf8NoBOM
```

PowerShell 5.1 fallback (no `utf8NoBOM` enum):

```powershell
$path = "C:\opencode-sandbox\.config\opencode\opencode.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($path, $jsonString, $utf8NoBom)
```
