# Epic 7.4 Future-Upgrade Watchlist

Date: 2026-03-22
Scope: non-blocking future concerns only

## Token/latency watch targets

- keep `opencode mcp list` near current pilot range (`3s-5s`)
- keep `tools/hello-stack/check_stack.py` execution near sub-second behavior
- continue recording jCodeMunch token-savings stats where exposed

## Upstream dependency watch

- OpenAgentsControl release/tag changes affecting selected payload structure
- Superpowers plugin/tag changes affecting required skill category names
- OpenCode CLI/runtime version changes affecting config precedence or plugin behavior
- jCodeMunch/jDocMunch index/version changes affecting retrieval workflow consistency

## Future tool-pruning opportunities

- reduce overlapping non-pilot tool surfaces if operator noise increases
- keep default visible tool set aligned to retrieval/edit/validation core path

## Pilot boundary note

- This watchlist is informational only and is not treated as a current pilot blocker.
