# Epic 6.2 Baseline vs Integrated Comparison Report

Date: 2026-03-22

## Benchmark set confirmation

The same frozen benchmark set from Epic 0 was used:

- `B1` runtime reaches usable model-backed state
- `B2` stack retrieval wiring is operational
- `B3` hello-stack wiring and targeted test readiness signal

Baseline source:

- `docs/integration-pilot/epic-0-benchmark-baseline.md`

Protocol/threshold source:

- `docs/integration-pilot/epic-6-evaluation-protocol.md`

## Snapshot references

- Branch: `main`
- Commit: `3306476c4ec5a98dd9f6c8d2413fe2dc3e2dccf5`
- Integrated run context: current pilot runtime with OAC payload `v0.7.1` and Superpowers pin `v5.0.5`

## Results by benchmark

### B1 - Runtime usable model-backed state

Baseline:

- status: pass
- failed-result count: `0`
- final quality: health/auth/route/model class gates passed

Integrated:

- `opencode auth list`: pass (`OpenAI oauth` visible)
- `opencode models`: pass (`openai/...`, `openai/...codex`, `llamacpp/...` present)
- `opencode debug skill`: required categories present (`using-superpowers`, `brainstorming`, `writing-plans`, `test-driven-development`, `systematic-debugging`)
- host endpoint checks from this build shell (`curl 127.0.0.1:5096` and `curl 127.0.0.1:8080`) were not reachable in this shell context

Outcome judgment:

- core runtime/auth/model outcome: pass
- quality signal: improved (required Superpowers categories now verified in integrated mode)
- comparability note: host endpoint subchecks require canonical host shell for direct re-timing

### B2 - Retrieval wiring operational

Baseline:

- time: `3.604s`
- failed-result count: `0`
- quality: pass (`3/3` MCP connected)

Integrated:

- command: `opencode mcp list`
- time: `4.403s`
- failed-result count: `0`
- quality: pass (`3/3` MCP connected)

Delta:

- time regression: `+22.2%`

Threshold judgment:

- pass (within `<=25%` tolerance)
- defect-count non-regression: pass

### B3 - Wiring check + targeted test readiness

Baseline:

- `tools/hello-stack/check_stack.py`: `0.243s`, pass, failed-result count `0`
- targeted pytest: `0.025s`, fail (`No module named pytest`), failed-result count `1`

Integrated:

- `tools/hello-stack/check_stack.py`: `0.245s`, pass, failed-result count `0`
- targeted pytest: `0.024s`, fail (`No module named pytest`), failed-result count `1`

Delta:

- check_stack time regression: `+0.8%`
- pytest readiness: unchanged failure state

Threshold judgment:

- timing threshold: pass
- defect-count non-regression: pass (no increase)

## Threshold summary

- Completion-time regression tolerance (`B2`,`B3`): pass
- Defect-count non-regression (`B1`,`B2`): pass for evaluated gates
- Minimum improvement signal: pass (B1 final quality improved via verified Superpowers category visibility)

## Attribution notes

- Improvement signal likely attributable to behavioral-discipline layer (Superpowers installation and verification)
- Stable edit/retrieval/test wiring likely attributable to established OAC payload path integrity + Serena/Munch baseline health
- `pytest` readiness remains blocked by environment dependency state, not by control-plane integration

## Decision linkage for regressions

- No regression exceeded threshold.
- No remediation/deferral/rejection action is required at this stage.
