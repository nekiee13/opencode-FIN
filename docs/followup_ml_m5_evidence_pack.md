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

- Operator: non-author operator in `[ICS]` (`oc-fin` container)
- Date: 2026-03-02
- Commit SHA: `c4a7a1b` (branch `m5-9-sop-validation-evidence`)
- Commands executed (`draft -> finalize -> parity -> publish`):
  - `/repo/.venv/bin/python scripts/followup_ml.py draft --round-id 26-1-11`
  - `/repo/.venv/bin/python scripts/followup_ml.py finalize --round-id 26-1-11`
  - `/repo/.venv/bin/python scripts/followup_ml.py board --round-id 26-1-11`
  - `/repo/.venv/bin/python scripts/followup_ml_parity.py compare --round-id 26-1-11`
  - publish step intentionally not executed because parity failed
- Outcome: SOP sequence was executed by a non-author operator, but parity failed (`failures=11`), so publish remained blocked per policy.
- Issues found and fixes: initial system `python3` run failed (`No module named 'pandas'`), rerun with `/repo/.venv/bin/python` completed; parity drift remained due DynaMix worker import error (`No module named 'src.model'`), missing `pmdarima` fallback path, and fixture lookup-date differences.
- Evidence links (parity report / CI run / publish proof):
  - parity report: `out/i_calc/followup_ml/reports/parity_26-1-11.md`
  - CI run: not applicable for local non-author container run
  - publish proof: not applicable (publish blocked by parity failure)

## Ownership and Escalation Matrix Approval

- Matrix document: `docs/followup_ml_ownership_escalation_matrix.md`
- Engineering owner approved:
- Operations owner approved:
- Approval evidence link:

## Go-live Checklist

- [ ] CI gate green
- [ ] Parity pass on required rounds
- [ ] No unresolved benchmark drift
- [x] Runbook validated by non-author user
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

## SOP Precheck Update 2026-03-02 (Sandbox Author Dry Run)

- Branch: `m5-9-sop-validation-evidence`
- Operator: OpenCode (author dry run; non-author validation still required)
- Round: `26-1-11`
- Commands executed:
  - `.venv/bin/python scripts/followup_ml.py draft --round-id 26-1-11`
  - `.venv/bin/python scripts/followup_ml.py finalize --round-id 26-1-11`
  - `.venv/bin/python scripts/followup_ml.py board --round-id 26-1-11`
  - `.venv/bin/python scripts/followup_ml_parity.py compare --round-id 26-1-11`
- Outcome: sequence executed end-to-end; parity compare failed (`failures=11`) in minimal dependency sandbox.
- Evidence: `out/i_calc/followup_ml/reports/parity_26-1-11.md`
- Notes: full non-author SOP evidence must be collected in production-like environment with complete dependency set and publish proof links.

## SOP Precheck Update 2026-03-02 (Sandbox Author Dependency-Complete Re-run)

- Branch: `m5-9-sop-validation-evidence`
- Operator: OpenCode (author rerun after full requirements install)
- Round: `26-1-11`
- Commands executed:
  - `.venv/bin/python scripts/followup_ml.py draft --round-id 26-1-11`
  - `.venv/bin/python scripts/followup_ml.py finalize --round-id 26-1-11`
  - `.venv/bin/python scripts/followup_ml.py board --round-id 26-1-11`
  - `.venv/bin/python scripts/followup_ml_parity.py compare --round-id 26-1-11`
- Outcome: parity still failed (`failures=11`) with DynaMix worker import failure and expected fixture differences in strict finalize lookup date.
- Evidence: `out/i_calc/followup_ml/reports/parity_26-1-11.md`
- Notes: non-author rerun should capture whether environment/flags match approved fixture conditions before publish readiness can be claimed.
