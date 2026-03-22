# Epic 2.3 OAC inventory summary

Date: 2026-03-22
Reference target version: `v0.7.1` (`e8497372eb16ea0e93c251aabac3b96cd82c7c16`)

## Start-state inventory (before import)

Observed local payload state at task start:

- `vendor-OpenAgentsControl.tar` contained only `vendor/OpenAgentsControl/` (empty top-level payload).
- `vendor/OpenAgentsControl/.opencode/` existed as reconstructed scaffold.
- Subdirectories `agent`, `config`, `context`, `plugin`, `skills`, and `tool` each contained only `.gitkeep`.
- `vendor/OpenAgentsControl/.opencode/README.md` explicitly stated incomplete vendor payload.

## Classification

State classification at task start: **scaffold-only**

Rationale:

- Required selected-version artifacts were missing.
- Approval/gating behavior could not be validated from payload content.
- Evaluation-support artifacts were not available in the vendored payload.

## Capability statement

At task start, OAC capabilities were **not testable** in this environment for pilot control-plane use.

## Missing required artifacts at task start

- `registry.json`
- `.opencode/agent/` content files
- `.opencode/command/` content files
- `.opencode/context/` content files
- `.opencode/plugin/` content files
- `.opencode/prompts/`
- `.opencode/tool/` content files
- `.opencode/skill/`
- `.opencode/profiles/`
- `.opencode/config.json`
- `.opencode/opencode.json`
- `evals/README.md`
- approval-gate evaluation artifact
