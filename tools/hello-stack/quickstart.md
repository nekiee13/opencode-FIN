# Hello-Stack Quickstart

This is a minimal end-to-end bootstrap for this repository.

## 0) License note

jCodeMunch and jDocMunch are dual-use projects. Review their non-commercial/commercial terms before enabling them in business environments.

## 1) Install retrieval servers locally

```bash
python -m pip install --upgrade jcodemunch-mcp jdocmunch-mcp
```

## 2) Create local OpenCode config

Copy `tools/hello-stack/opencode.mcp.example.json` into your active OpenCode project config file, then set:

- container runtime path: `/workspace/.config/opencode/opencode.json`
- host mirror path (Docker bind mount): `C:\opencode-sandbox\.config\opencode\opencode.json`

- `enabled: true` for `jcodemunch` and `jdocmunch` when ready
- API key env values only if needed

## 3) Validate stack wiring

```bash
python tools/hello-stack/check_stack.py
opencode mcp list
```

Expected:

- `mcp:serena` is `PASS`
- `mcp:jcodemunch` and `mcp:jdocmunch` become `PASS` after enabling/configuring
- OAC symlink paths under `.opencode/` are not broken

## 4) Run one smoke task

Use a small, low-risk task (for example one test update) with this sequence:

1. jCodeMunch: search_symbols -> get_symbol
2. jDocMunch: search_sections -> get_section
3. Superpowers: brainstorming + writing-plans + test-driven-development
4. Serena: perform symbol-aware edits
5. OAC: enforce approval between workflow steps
6. Verify with tests

## 5) Capture baseline and post-enable metrics

Track these before/after enabling retrieval + skills:

- task completion time
- tests pass/fail count
- changed files count
- token usage (if available from your client)
