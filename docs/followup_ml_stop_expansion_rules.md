# Follow-up ML Stop Expansion Rules (M5)

This policy freezes scope during M5 until sign-off criteria are met.

## Effective window

- Start: policy approval
- End: M5 sign-off complete

## Hard rules

- No new models, tickers, metrics, dashboard sections, or workflows.
- No schema expansion for required fields/tables/formats.
- No behavior changes that alter benchmark parity semantics.
- No new external services or credentialed integrations.

Allowed during freeze:

- parity and correctness bug fixes
- determinism hardening
- CI gate hardening
- runbook/SOP and ownership updates
- rollback safety updates

## Required labels

- `m5-scope`: in-scope hardening work
- `m5-expansion-exception`: approved expansion exception

Label bootstrap:

1. Run GitHub Actions workflow: `followup-ml-label-bootstrap`.
2. Confirm labels exist in repository label settings.

## Exception process

Expansion requires both:

- Engineering Owner approval
- Operations Owner approval

Use issue template: `.github/ISSUE_TEMPLATE/m5-expansion-exception.yml`.

## PR policy

- Every PR must include exactly one of `m5-scope` or `m5-expansion-exception`.
- Exception PRs must complete all required sections in PR body:
  - Business reason
  - Scope delta
  - Parity impact analysis
  - Rollback plan
  - Owner
  - Approver(s)

Enforced by workflow:

- `.github/workflows/followup-ml-scope-governance.yml`

## Weekly audit step

Perform once per week and paste results in the evidence pack:

1. `m5-expansion-exception` merges during period
2. all exception PRs include required approvals
3. violations count is exactly zero

Suggested query examples:

```bash
gh pr list --state merged --label m5-expansion-exception --search "merged:>=YYYY-MM-DD"
gh pr list --state merged --search "merged:>=YYYY-MM-DD -label:m5-scope -label:m5-expansion-exception"
```
