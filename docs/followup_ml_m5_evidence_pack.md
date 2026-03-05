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
| YYYY-MM-DD | PASS/FAIL | PASS/FAIL | none/resolved/open | |
| YYYY-MM-DD | PASS/FAIL | PASS/FAIL | none/resolved/open | |
| YYYY-MM-DD | PASS/FAIL | PASS/FAIL | none/resolved/open | |

## Benchmark Drift Register

| Round | Status | Root cause | Resolution or acceptance | Owner |
|:--|:--|:--|:--|:--|
| 26-1-06 | | | | |
| 26-1-09 | | | | |
| 26-1-11 | | | | |

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

- [ ] CI gate green
- [ ] Parity pass on required rounds
- [ ] No unresolved benchmark drift
- [ ] Runbook validated by non-author user
- [ ] Ownership and escalation matrix confirmed
- [ ] Publish destination and rollback targets verified

## Rollback Drill

- Drill date:
- Trigger simulated:
- Procedure used:
- Time to recover:
- Follow-up actions:

## Final Approval

- Engineering Owner:
- Operations Owner:
- Sign-off date:
- Decision: GO / NO-GO

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

## M5 Closure Update 2026-03-05

### Work item status
- #5 Go-live checklist and rollback procedure: done
- #5 Rollback drill validation: done
- #6 Consecutive cycle pass criteria: pending evidence
- #6 Drift closure criteria: pending evidence
- #6 Final owner sign-off: pending

### Rollback drill record
- Date: 2026-03-05
- Round: 26-1-11
- Method: snapshot, simulated corruption, restore, checksum compare, parity compare
- Recovery time: less than 1 second
- Evidence: out/i_calc/followup_ml/reports/rollback_drill_20260305T230207Z

### Final sign-off gate
- At least two consecutive cycles with CI PASS and parity PASS
- No unresolved benchmark drift
- No open scope-governance violations
- Non-author runbook validation link recorded
- Engineering and Operations GO decision recorded
