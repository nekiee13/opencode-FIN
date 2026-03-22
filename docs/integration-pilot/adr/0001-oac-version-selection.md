# ADR 0001: OAC target version selection

Status: accepted

## Context

Epic 2 requires a pinned OpenAgentsControl (OAC) version before payload import.

Required feature classes for pilot gating are:

- registry/control manifest support
- approval/gating behavior support
- evaluation support

Evidence used:

- GitHub release history and tags for `darrenhinde/OpenAgentsControl`
- Versioned repository tree checks at `v0.1.0`, `v0.5.0`, and `v0.7.1`
- Local vendor state evidence showing placeholder scaffold only

Candidate versions considered:

- `v0.1.0` (`28131d3559cbb2431645b2f79d958382d1cb75b7`)
- `v0.5.0` (`25041f77fbcc2a07307678bc4f34de557bf7ec8d`)
- `v0.7.1` (`e8497372eb16ea0e93c251aabac3b96cd82c7c16`)

Feature checks across candidates:

- `registry.json` present
- `evals/README.md` present
- approval-gate test artifact present
  - `evals/agents/.../approval-gate/05-approval-before-execution-positive.yaml`

Documentation sufficiency note:

- Documentation is sufficient for tagged release history and high-level feature signals.
- A strict per-version feature matrix is not published as a single canonical table.

## Decision

Target version is pinned to release tag `v0.7.1` and commit `e8497372eb16ea0e93c251aabac3b96cd82c7c16`.

Reasoning:

- Required feature classes are observable in this version.
- Latest stable tag reduces known drift against current upstream structure.
- This choice aligns with the pilot risk posture for controlled import and rollback.

Minimum observed version with required feature class evidence appears to be `v0.1.0`, but `v0.7.1` is selected for maturity and current schema alignment.

Definition of complete payload for this selected version (pilot):

- `registry.json`
- `.opencode/agent/`
- `.opencode/command/`
- `.opencode/context/`
- `.opencode/plugin/`
- `.opencode/prompts/`
- `.opencode/tool/`
- `.opencode/skill/`
- `.opencode/profiles/`
- `.opencode/config.json`
- `.opencode/opencode.json`
- `evals/README.md`
- approval-gate evaluation artifact

## Consequences

- Epic 2.4 import must use this exact tag/commit pair.
- Epic 2.5 completeness checks are measured against this payload definition.
- Upgrade work requires a new ADR decision or explicit supersession.
