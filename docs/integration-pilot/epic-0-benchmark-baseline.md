# Epic 0 Pre-Integration Benchmark Baseline

Date: 2026-03-22

## Snapshot pinning

- Repo branch: `main`
- Repo commit: `3306476c4ec5a98dd9f6c8d2413fe2dc3e2dccf5`
- Procedure document snapshot: `tools/hello-stack/quickstart.md` at the same commit
- Runtime objects observed in transcript: OpenCode `1.1.52`, Docker `29.1.3`, llama.cpp model `Devstral-Small-2-24B-Instruct-2512-UD-IQ3_XXS.gguf`

## Benchmark set (outcome-oriented)

### B1 - Runtime reaches usable model-backed state

Outcome target:

- OpenCode runtime is healthy.
- OAuth credential is visible.
- Host-to-container model routing works.
- Final model registry contains required classes (`openai/...`, `openai/...codex`, `llamacpp/...`).

Baseline result:

- Status: pass (all gates passed in one sequence).
- Total time to completed state: coarse `<= 3 minutes` from transcript window (exact per-gate timer not instrumented).
- Defect/failed-result count: `0`.
- Rework cycles: `0`.
- Final test outcome quality: all defined runtime gates passed.

Evidence references:

- `curl http://127.0.0.1:5096/global/health` -> `{"healthy":true,"version":"1.1.52"}`
- `docker exec oc-fin-opencode opencode auth list` -> includes `OpenAI oauth`
- `docker exec oc-fin-opencode curl http://host.docker.internal:8080/v1/models` -> valid JSON
- `docker exec oc-fin-opencode opencode models` -> includes required model families

### B2 - Stack retrieval wiring is operational

Outcome target:

- Serena, jCodeMunch, and jDocMunch are connected from project config.

Baseline result:

- Command: `opencode mcp list`
- Total time to completed check: `3.604s`
- Defect/failed-result count: `0`
- Rework cycles: `0`
- Final test outcome quality: pass (`3/3` MCP servers connected)

### B3 - Validation check and test readiness signal

Outcome target:

- Hello-stack wiring check passes.
- One targeted test command executes successfully.

Baseline result:

- Wiring check command: `python3 tools/hello-stack/check_stack.py`
  - Time: `0.243s`
  - Result: pass
  - Failed-result count: `0`
- Targeted test command: `python3 -m pytest tests/test_infra.py::test_import_loading_module -q`
  - Time: `0.025s`
  - Result: fail (`No module named pytest`)
  - Failed-result count: `1`
  - Rework cycles: `0` (no remediation attempted in baseline phase)

Quality interpretation:

- Wiring quality is currently good.
- Test-execution readiness is currently blocked by missing test dependency in this shell environment.

## Optional metrics

- Token usage: not exposed in these benchmark commands.
- Latency: captured only as command elapsed time where instrumented.
