# Epic 3.2 Superpowers installation log

Date: 2026-03-22
Install scope: canonical pilot runtime path only

## Installation source

- Upstream repo: `https://github.com/obra/superpowers`
- Install reference: `.opencode/INSTALL.md` from upstream main branch
- Selected pin for pilot: `v5.0.5`
- Plugin entry used:
  - `superpowers@git+https://github.com/obra/superpowers.git#v5.0.5`

## Applied runtime config change

- Active project config in canonical runtime was updated at:
  - `/workspace/.config/opencode/opencode.json`
- Global config was not modified.
- Installation remained limited to pilot project scope.

Observed project config state after update:

- `plugin` contains `superpowers@git+https://github.com/obra/superpowers.git#v5.0.5`
- `mcp` block in project file listed `serena`
- Runtime MCP surface still resolved `serena`, `jcodemunch`, `jdocmunch` (merged behavior)

## Startup evidence after install

Observed startup log lines include:

- `service=plugin path=superpowers@git+https://github.com/obra/superpowers.git#v5.0.5 loading plugin`

Observed skill-discovery evidence:

- `opencode debug skill` returned `14` skills.
- Required skill categories were present:
  - `using-superpowers`
  - `brainstorming`
  - `writing-plans`
  - `test-driven-development`
  - `systematic-debugging`

## Runtime continuity check

- OpenCode command execution remained functional after install probe.
- No install interruption remained unresolved in the local validation run.
- Canonical runtime container checks also remained healthy after config update.

## Notes

- Legacy symlink-style Superpowers installation was not used.
- Plugin registration followed upstream one-line plugin method.
