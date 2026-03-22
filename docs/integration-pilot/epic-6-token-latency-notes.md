# Epic 6.3 Optional Token/Latency Notes

Date: 2026-03-22
Scope: lightweight pilot budget hints only

## Latency observations (integrated run)

- `opencode mcp list`: observed around `4.4s`
- `python3 tools/hello-stack/check_stack.py`: observed around `0.245s`
- `python3 -m pytest tests/test_infra.py::test_import_loading_module -q`: observed around `0.024s` (fails due missing pytest module)

Practical pilot ranges (rough):

- retrieval wiring check (`opencode mcp list`): acceptable around `3s-5s`
- hello-stack local wiring check: acceptable around `<1s`

## Token observations (where exposed)

- jCodeMunch session stats exposed token savings:
  - session tokens saved: `1386`
  - total tokens saved in session context: `2677`
- jDocMunch does not expose equivalent aggregate token totals in the same form.

## Use guidance

- These values are advisory only for pilot upgrades.
- They are not a hard gate for pilot keep/revise decisions.
