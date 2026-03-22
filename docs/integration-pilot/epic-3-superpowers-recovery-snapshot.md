# Epic 3.1 Superpowers pre-install recovery snapshot

Date: 2026-03-22
Scope: canonical pilot runtime only

## Snapshot objective

A rollback baseline is captured before Superpowers installation starts.

## Pre-install state evidence

- Project config file exists: `C:\opencode-sandbox\.opencode\opencode.json` (mirror: `/repo/.opencode/opencode.json`)
- Global config file exists: `/home/opencode/.config/opencode/opencode.json`
- `plugin` key is absent in both project and global config files.
- Superpowers plugin file path is absent: `/home/opencode/.config/opencode/plugin/superpowers.js`
- Superpowers clone path is absent: `/home/opencode/.config/opencode/superpowers/`
- Superpowers skills path is absent: `/home/opencode/.config/opencode/superpowers/.opencode/skill`

## Rollback entry points

- Config rollback: restore pre-install `opencode.json` backup in project scope.
- Plugin rollback: remove Superpowers plugin entry from `plugin` array.
- Cache/runtime rollback: restart OpenCode runtime after config restore.
- Legacy path cleanup rollback (if used): remove stale `plugin/superpowers.js` and stale superpowers clone directory.

## Rollback steps (canonical)

1. Stop OpenCode runtime container layer.
2. Restore backed-up `C:\opencode-sandbox\.opencode\opencode.json`.
3. Remove any Superpowers plugin or clone leftovers, if present.
4. Start OpenCode runtime container layer.
5. Re-run health, auth, model, and skill checks.

## Post-rollback expected state

- OpenCode health endpoint returns healthy JSON.
- OAuth credential remains visible.
- Model registry gates continue to pass.
- Superpowers skill discovery is absent again (baseline-equivalent state).
- No stale symlink or plugin-file errors are present in startup/log output.
