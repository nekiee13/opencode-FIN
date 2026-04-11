# Follow-up ML Ownership and Escalation Matrix (M5)

Last reviewed: 2026-04-11
Source commit: `055c7bc`

This document defines operational ownership for the weekly Follow-up ML run.

## Coverage

- Workflow: `draft -> finalize -> parity -> publish`
- Systems: state, weights, dashboards, parity reports, CI gate outcomes

## Ownership Matrix

| Role | Owner | Backup | Responsibilities |
|:--|:--|:--|:--|
| Primary operator | `@followup-ml-primary` | `@followup-ml-backup` | Executes weekly workflow and records evidence. |
| Engineering owner | `@fin-eng-owner` | `@fin-eng-backup` | Technical triage, parity drift fixes, release decisions. |
| Operations owner | `@fin-ops-owner` | `@fin-ops-backup` | Publish approvals, incident coordination, comms. |

## Escalation Path and Response Targets

| Condition | Initial owner | Escalation path | Target response |
|:--|:--|:--|:--|
| CI gate failure | Primary operator | Engineering owner -> Operations owner | 30 minutes |
| Parity drift on benchmark rounds | Primary operator | Engineering owner -> Operations owner | 30 minutes |
| Publish blocked at cutoff window | Operations owner | Engineering owner -> Operations owner | 15 minutes |
| Rollback trigger fired | Operations owner | Engineering owner -> Operations owner | Immediate |

## Publish Window and Backup Coverage

- Standard publish window: `Fridays 16:00-18:00 local runtime timezone`
- Backup operator on-call window: `Fridays 15:30-18:30 local runtime timezone`
- No single-person dependency is allowed during publish window.

## Handoff Notes (Non-author Run)

- Operator handoff artifact: link command transcript and generated artifact paths.
- Confirm final statuses before publish: CI green, parity pass, no unresolved benchmark drift.
- If override mode was used, confirm break-glass fields are present in round context.

## Approval

- Engineering owner approval: `Recorded`
- Operations owner approval: `Recorded`
- Approval date: `2026-03-16`
