# Epic 3.4 Superpowers rollback drill log

Date: 2026-03-22

## Drill A: rollback from normal installed state

Scenario:

- Superpowers plugin was active in project config.
- Full rollback was simulated by removing the plugin entry.

Observed result:

- After rollback removal: `skill_count=0`, `using-superpowers=false`
- After reinstall restore: `skill_count=14`, `using-superpowers=true`

Conclusion:

- Full rollback and reinstall path was successful in this validation run.

## Drill B: partial-failure recovery

Scenario:

- Partial failure was induced by setting plugin tag to a non-existent value.

Observed failure evidence:

- Startup attempted to load invalid plugin reference.
- Error was observed:
  - `BunInstallFailedError` from invalid plugin reference.

Recovery action:

- Plugin entry was restored to valid pinned value.
- Skill-discovery check was re-run.

Observed recovery result:

- Required skills returned and passed visibility checks.

Conclusion:

- Partial-failure rollback handling was tested and recovery succeeded.
