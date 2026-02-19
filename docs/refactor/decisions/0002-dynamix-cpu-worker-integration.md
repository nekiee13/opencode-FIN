# 0002 - DynaMix CPU-Only Worker Integration

## Status

Accepted

## Context

FIN adds optional DynaMix forecasting support as a new canonical model path (`DYNAMIX`).

Key constraints:

- Phase-1 ownership requires canonical logic in `src/` and thin `compat/` delegation.
- Phase-1 worker protocol requires structured JSON on `stdout`.
- DynaMix upstream package uses `src.*` imports, which conflicts with FIN's own `src` package when loaded in-process.
- User requirement: DynaMix must run CPU-only.

## Decision

Integrate DynaMix through a dedicated worker protocol with CPU enforcement:

1. Canonical API: `src.models.dynamix.predict_dynamix`
2. Worker CLI: `scripts/workers/dynamix_worker.py`
3. IPC envelope:
   - `protocol_version`
   - `ok`
   - `artifact_csv` on success
   - `error` object on failure
4. CPU-only guardrails:
   - Worker sets `CUDA_VISIBLE_DEVICES=""`
   - Worker uses `torch.device("cpu")`
5. Facade integration:
   - `src.models.facade` gains `run_dynamix`
   - `MODEL_PRIORITY_DEFAULT` now includes `DYNAMIX`
6. Legacy compatibility:
   - `compat/Models.py` re-exports `predict_dynamix`
   - `src.models.compat_api.predict_dynamix` delegates to canonical model

## Consequences

Positive:

- Avoids namespace collision between FIN `src.*` and DynaMix `src.*`.
- Preserves import safety at module import time.
- Preserves deterministic, machine-readable worker protocol.
- Keeps CPU-only behavior explicit and testable.

Trade-offs:

- Adds subprocess overhead versus in-process execution.
- Requires DynaMix repository checkout path configuration when not present in default location.

## Follow-up

- Add optional integration tests with a real DynaMix checkout in CI environments that can host model downloads.
- Evaluate a future packaging strategy to remove `src.*` namespace collision risk without worker isolation.
