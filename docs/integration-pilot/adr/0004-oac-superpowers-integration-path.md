# ADR 0004: OAC × Superpowers integration path

Status: accepted

## Context

Epic 4 requires an explicit decision for the relationship between OAC and Superpowers.

Options considered:

- hook-native only
- adapter required
- adapter deferred

Pilot constraints:

- fixed scope and single-operator execution
- requirement to keep integration auditable and recoverable
- no new governance layers before pilot decision point

## Decision

Decision: **hook-native only** for current pilot.

Definition in this pilot:

- Superpowers remains a client/runtime plugin and skill layer.
- OAC remains control-plane authority for workflow gates and approval artifacts.
- No direct adapter/plugin coupling is introduced between OAC internals and Superpowers internals.

Rationale:

- existing pilot evidence already validates Superpowers plugin loading and skill visibility
- OAC authority model is captured via workflow artifacts and gate records without additional adapter complexity
- adapter introduction would increase pilot scope and dependency risk without required value for current exit criteria

## Consequences

- no claim that Superpowers is an OAC plugin is valid in this pilot
- integration occurs by contract (artifact interface + authority boundaries), not by runtime coupling
- if future pilot evidence requires tighter coupling, a new ADR can supersede this decision after pilot decision point

Policy consistency note:

- Tool-visibility and retrieval/edit policy remains valid under hook-native mode.
- No policy changes are required before hello-stack execution.
