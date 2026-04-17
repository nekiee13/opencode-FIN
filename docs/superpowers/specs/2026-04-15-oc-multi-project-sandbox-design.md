# OC Multi-Project Sandbox Design

## Scope

Design a reusable OpenCode operating model for six projects on Win11 (`FIN`, `Marker`, `LLM Wiki`, `JSON`, `Loto`, `Games`) using strong isolation, repeatable setup, and fast switching.

## Architecture

Use a hub-and-spoke model:

- One golden repository: `opencode-agent-core`
- One isolated runtime instance per project: `oc-<project>`
- One project repo mount per runtime

Runtime type is default Docker/WSL2 Linux, with fallback to isolated Windows runtime if a project proves Linux-incompatible.

## Components and Boundaries

- **Core repo (`opencode-agent-core`)**: reusable OC stack, templates, scripts, docs, checks.
- **Sandbox template**: folder contract, environment contract, mount policy, startup gates.
- **Project runtime instance**: project-local config/secrets/logs/state/cache/backups.
- **Project repositories**: independent source repositories, not cross-mounted.
- **Governance**: tagged core versions; instances pin and upgrade intentionally.

## Data and Operational Flow

1. Provision project runtime from template.
2. Bind exactly one project repo + project-local secrets.
3. Run readiness gates (`opencode`, MCP 3/3, required skills, mount integrity).
4. Operate project tasks with project-local logs/artifacts.
5. Upgrade with staged promotion and rollback snapshot.
6. Restore with per-runtime runbook and validation certification.

## Safety and Recovery

- Hard startup gates before `READY`.
- Drift detection against pinned core version.
- Per-instance failure containment.
- One-command rollback to last known-good snapshot.
- Secret boundary enforcement and redacted logs.
- Per-instance audit artifacts.

## Testing and Acceptance

- Template validation (structure, config, mount policy)
- Readiness gate validation
- Isolation tests (path/env/cache leakage)
- Upgrade + rollback tests
- Restore certification tests

30-day success criteria:

- New sandbox provisioned in under 30 minutes
- Zero cross-project leakage incidents
- Fast, predictable runtime switching

## Scalability

The design supports `P7+` with no architecture change through an `add-project` workflow that creates, validates, and certifies a new runtime instance from the same template.
