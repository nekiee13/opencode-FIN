# Epic 0 Baseline Snapshot

Date: 2026-03-22  
Scope: single-operator pilot (fixed-plan execution)

## Evidence sources

- Safe opening sequence operator transcript captured on 2026-03-22.
- Repository inspection from `/repo` at commit `3306476c4ec5a98dd9f6c8d2413fe2dc3e2dccf5`.
- Local runtime checks: `opencode --version`, `opencode mcp list`, and config file inspection.

## Runtime baseline

- Client/runtime version: OpenCode `1.1.52`.
- Host OS signal: Windows + Docker Desktop (WSL2 kernel `6.6.87.2-microsoft-standard-WSL2`).
- Canonical workspace root for pilot runtime: `C:\opencode-sandbox`.
- Canonical OpenCode endpoint for pilot runtime: `http://127.0.0.1:5096`.

## Config roots (observed)

- Project-local config root: `C:\opencode-sandbox\.opencode\` (pilot runtime object).
- Linux mirror project-local config root: `/repo/.opencode/`.
- Global config root: `/home/opencode/.config/opencode/`.
- Credential store: `/home/opencode/.local/share/opencode/auth.json`.

## MCP surface from canonical project config

Observed from `opencode mcp list` in `/repo`:

- `serena` -> connected
- `jcodemunch` -> connected
- `jdocmunch` -> connected

## OAC state summary

Classification: **scaffold-only**

Observed checks:

- `.opencode` symlinks target `vendor/OpenAgentsControl/.opencode/*`.
- `vendor/OpenAgentsControl/README.md` captures the current vendored payload context; pilot logs note the earlier scaffold-only state.
- `tools/hello-stack/oac.registry.example.json` contains `TODO` execution placeholders.

Current implication:

- Approval/gating and evaluation behavior are not yet operationally validated from complete upstream assets.

## Superpowers state summary

Classification: **absent** (payload evidence) / **operationally unvalidated** (runtime behavior)

Observed checks:

- `vendor/OpenAgentsControl/.opencode/skills/` contains only `.gitkeep`.
- No repository hook files matching `*hook*` were found.
- No required skill-pack artifacts (`using-superpowers`, `brainstorming`, `writing-plans`, `test-driven-development`, `systematic-debugging`) were found in repo payload.

Current implication:

- Superpowers behavior cannot be treated as active until installation and startup checks in Epic 3 are completed.
