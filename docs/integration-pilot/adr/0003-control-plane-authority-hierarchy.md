# ADR 0003: Control-plane authority hierarchy

Status: accepted

## Context

Epic 4 requires explicit ownership boundaries across OAC, Superpowers, Serena, and Munch retrieval servers.

Pilot constraints:

- single-operator execution
- bounded scope with fixed artifact classes
- evidence-based transitions between workflow stages

## Decision

Authority hierarchy is defined as follows.

1. **OAC (control-plane authority)**
   - owns workflow stage transitions
   - owns approval/gate decisions
   - owns evaluation acceptance for stage completion
2. **Superpowers (behavioral preflight authority)**
   - owns plan discipline and tests-first behavior
   - owns startup skill posture checks
   - cannot override OAC gate outcomes
3. **Retrieval plane (jCodeMunch + jDocMunch)**
   - owns retrieval evidence for code and docs
   - provides traceable references used by planning and edits
   - does not perform edits or approvals
4. **Edit plane (Serena preferred semantic editor)**
   - owns semantic edit/refactor operations
   - returns edit result status and failure details
   - does not approve stage transitions
5. **Test/result plane (runner + report artifact)**
   - owns pass/fail evidence for executed checks
   - provides final result artifact for OAC transition decision

Conflict resolution order:

- OAC gate decision -> final authority
- if OAC has no decision artifact, stage transition is denied
- Superpowers guidance applies only inside an approved stage
- retrieval and edit claims without evidence are treated as invalid

Linked policy/spec artifacts:

- workflow artifact interface: `docs/integration-pilot/epic-4-workflow-artifact-spec.md`
- retrieval/edit/tool visibility policy: `docs/integration-pilot/epic-4-operator-policy.md`

Required conflict-case handling:

- **preflight failure**
  - gate transition denied
  - recovery: regenerate preflight artifact and re-evaluate
- **gate denial**
  - no edit action allowed
  - recovery: satisfy missing gate requirements
- **missing retrieval evidence**
  - planning stage blocked
  - recovery: collect jCodeMunch/jDocMunch references
- **edit failure**
  - test stage blocked
  - recovery: capture edit error, fix, and re-run edit before tests

## Consequences

- Stage advancement becomes evidence-driven instead of narrative-driven.
- Operational ambiguity is reduced for single-operator troubleshooting.
- Superpowers remains a behavior layer, not a gate authority.
