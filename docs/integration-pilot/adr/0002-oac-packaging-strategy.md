# ADR 0002: OAC packaging strategy

Status: accepted

## Context

Epic 2 requires controlled import/install with reproducibility, update clarity, and rollback safety.

Packaging options considered:

- vendored snapshot in repository
- direct runtime install from upstream scripts
- hybrid approach (runtime install + selective vendoring)

Constraints:

- Pilot requires auditable source provenance.
- Rollback must be fast and local.
- Runtime should avoid hidden drift during pilot runs.

## Decision

The selected strategy is a vendored snapshot under `vendor/OpenAgentsControl/`, pinned to tag `v0.7.1` and commit `e8497372eb16ea0e93c251aabac3b96cd82c7c16`.

Update method:

- Download upstream tagged tarball.
- Record source URL, tag, commit, archive checksum, and import date.
- Replace vendored directory with extracted snapshot.
- Re-run stack and path-integrity checks.

Rollback method:

- Restore the timestamped backup directory created immediately before replacement.
- Re-run `python3 tools/hello-stack/check_stack.py`.
- Verify `.opencode` symlink targets resolve.

## Consequences

- Reproducibility is improved because payload content is pinned and stored locally.
- Repository size increases due vendored source content.
- Update burden is manual but predictable.
- Runtime drift risk is reduced relative to direct live-install behavior.
