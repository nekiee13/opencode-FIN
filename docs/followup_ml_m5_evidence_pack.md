# Follow-up ML M5 Evidence Pack

Use this document to record objective sign-off evidence.

## Scope Freeze Audit

- Audit window start:
- Audit window end:
- Unapproved expansion merges count:
- Exception PRs reviewed:

Links:

- PR query (`m5-expansion-exception`):
- PR query (missing both labels):

## Consecutive Cycle Evidence

| Cycle | CI Gate | Parity | Drift on benchmark rounds | Notes |
|:--|:--|:--|:--|:--|
| 2026-03-06 | PASS | PASS | none | PR #14 checks passed (`https://github.com/nekiee13/opencode-FIN/pull/14/checks`); merge commit `82c1ab0`. |
| YYYY-MM-DD | PASS/FAIL | PASS/FAIL | none/resolved/open | |
| YYYY-MM-DD | PASS/FAIL | PASS/FAIL | none/resolved/open | |

## Benchmark Drift Register

| Round | Status | Root cause | Resolution or acceptance | Owner |
|:--|:--|:--|:--|:--|
| 26-1-06 | none | n/a | deterministic fixture parity gate PASS on 2026-03-06 (`PR #14` checks) | Follow-up ML gate |
| 26-1-09 | none | n/a | deterministic fixture parity gate PASS on 2026-03-06 (`PR #14` checks) | Follow-up ML gate |
| 26-1-11 | none | n/a | deterministic fixture parity gate PASS on 2026-03-06 (`PR #14` checks) | Follow-up ML gate |

## Runbook Validation (Non-author)

- Operator:
- Date:
- Commands executed (`draft -> finalize -> parity -> publish`):
- Outcome:
- Issues found and fixes:

## Ownership and Escalation Matrix Approval

- Matrix document: `docs/followup_ml_ownership_escalation_matrix.md`
- Engineering owner approved:
- Operations owner approved:
- Approval evidence link:

## Go-live Checklist

- [x] CI gate green (evidence: `https://github.com/nekiee13/opencode-FIN/pull/14/checks`)
- [x] Parity pass on required rounds (evidence: deterministic fixture parity gate in `PR #14` checks)
- [x] No unresolved benchmark drift (evidence: Benchmark Drift Register entries for `26-1-06`, `26-1-09`, `26-1-11`)
- [x] Runbook validated by non-author user (evidence: `https://github.com/nekiee13/opencode-FIN/pull/13`)
- [ ] Ownership and escalation matrix confirmed (evidence: owner approval fields pending)
- [x] Publish destination and rollback targets verified (evidence: `out/i_calc/followup_ml/reports/rollback_drill_20260305T230207Z/summary.txt`)

## Rollback Drill

- Drill date:
- Trigger simulated:
- Procedure used:
- Time to recover:
- Follow-up actions:

## Final Approval

- Engineering Owner: pending
- Operations Owner: pending
- Sign-off date: pending
- Decision: NO-GO (pending second consecutive cycle PASS and owner approvals)

## Weekly Audit Update 2026-03-01

- Exception merges: 0
- Merged PRs missing both scope labels: 0
- Violations: 0
- Tracker comment: https://github.com/nekiee13/opencode-FIN/issues/2#issuecomment-3981292133

## CI Recovery Update 2026-03-01

- followup-ml-gate run 22555556573: PASS
- Commit: a09d728
- Fix: requirements.txt pin numpoly==1.2.14 (numpy 1.26 compatible)
- Tracker comment: https://github.com/nekiee13/opencode-FIN/issues/2#issuecomment-3981324453

## Final Sync Update 2026-03-01

- Non-sandbox status: clean (master...origin/master)
- Latest followup-ml-gate run 22555798195: PASS
- Head commit: 892742d
- Tracker comment: https://github.com/nekiee13/opencode-FIN/issues/2#issuecomment-3981340619

## Checkpoint Update 2026-03-01 (Post-Sync)

- Head commit: 2b5f662
- Latest followup-ml-gate run 22555978831: PASS
- Sandbox -> GitHub -> non-sandbox sync: complete
- Tracker comment: https://github.com/nekiee13/opencode-FIN/issues/2#issuecomment-3981357925

## M5 Closure Update 2026-03-06

### Work item status
- #5 Go-live checklist and rollback procedure: done
- #5 Rollback drill validation: done
- #6 Consecutive cycle pass criteria: in progress (1 of 2 cycles recorded)
- #6 Drift closure criteria: done for current cycle (no unresolved benchmark drift)
- #6 Final owner sign-off: pending

### Evidence links
- PR: `https://github.com/nekiee13/opencode-FIN/pull/14`
- Checks: `https://github.com/nekiee13/opencode-FIN/pull/14/checks`
- Merge commit: `https://github.com/nekiee13/opencode-FIN/commit/82c1ab0`
- Rollback drill: `out/i_calc/followup_ml/reports/rollback_drill_20260305T230207Z`

### Next closure condition
- Record one additional consecutive cycle with CI PASS + parity PASS, then collect owner approvals and update Final Approval to GO.

