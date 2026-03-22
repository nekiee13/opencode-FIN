# Epic 4.3 Retrieval/Edit/Tool-Visibility Policy

Date: 2026-03-22
Scope: pilot workspace policy

## Preferred retrieval path

- Code retrieval default: `jCodeMunch`
  - preferred sequence: `search_symbols` -> `get_symbol` (or equivalent context bundle)
- Documentation retrieval default: `jDocMunch`
  - preferred sequence: `search_sections` -> `get_section`

## Preferred edit path

- Semantic edit/refactor default: `Serena`
- Fallback edit path: direct patch/edit tools only when Serena cannot address the target safely

## Approved full-file read exceptions

Full-file reads are allowed only when one of the following is true:

- file length is small enough that symbol retrieval adds no value
- non-code artifact requires complete context (for example, short markdown policy files)
- symbol lookup failed and boundary triage requires raw file inspection

When exception is used, run evidence must note the exception reason.

## Pilot tool visibility policy

Default visible tools:

- retrieval: jCodeMunch, jDocMunch
- semantic editing: Serena
- execution and validation: Bash, Read, Glob, Grep, apply_patch

Default hidden/noise-reduced tools:

- non-pilot image generation and unrelated helper families
- redundant overlap tools when primary tool is available for the same task class

## Control-plane linkage

This policy is referenced by:

- `docs/integration-pilot/adr/0003-control-plane-authority-hierarchy.md`
- `docs/integration-pilot/adr/0004-oac-superpowers-integration-path.md`
