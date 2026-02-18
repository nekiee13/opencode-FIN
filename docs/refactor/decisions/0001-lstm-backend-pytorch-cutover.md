# ADR 0001 - LSTM Backend Cutover (TensorFlow -> PyTorch)

- Status: Accepted
- Date: 2026-02-18
- Owners: Forecasting Core
- Scope: Phase-1 Path Stabilization

## Context

The FIN codebase currently uses TensorFlow/Keras for LSTM forecasting. The active requirements pin an older TensorFlow stack, which increases dependency friction and environment maintenance cost.

Within this repository, TensorFlow is used for LSTM paths only. Other forecasting stacks (ARIMAX/ETS/VAR/GARCH/PCE/PyCaret worker) are not hard-bound to TensorFlow.

Phase-1 requires:

- canonical modeling logic in `src/`
- `compat/` as delegation-only shims
- deterministic output contracts across entrypoints

## Decision

We will migrate LSTM forecasting from TensorFlow/Keras to PyTorch.

This is a hard backend cutover for LSTM logic (not a long-term dual backend). Temporary fallback code is allowed only during implementation branches and must not remain after merge unless explicitly approved in a separate ADR.

## LSTM Contract Freeze (Phase-1)

The external LSTM forecast contract is frozen and must remain stable through this migration.

### Required output schema

- `LSTM_Pred`: point forecast
- `LSTM_Lower`: lower interval/quantile forecast
- `LSTM_Upper`: upper interval/quantile forecast

### Required index semantics

- Index type: `pandas.DatetimeIndex`
- Frequency: business-day (`B`) progression
- Start: first business day after the last observed input timestamp
- Length: exactly `FH`

### Required behavior

- LSTM remains optional and capability-gated.
- If backend dependency is unavailable, LSTM path degrades gracefully (returns `None` in legacy/canonical optional paths) with deterministic logging.
- Exogenous regressor support and recursive FH forecasting behavior remain available.

## Cutover Policy

- Canonical implementation location: `src/models/lstm.py`
- Legacy call sites must delegate to canonical implementation rather than keep parallel algorithmic code.
- `compat/` must not contain LSTM algorithm implementations.
- TensorFlow-specific runtime setup and capability checks are replaced by torch-based equivalents where applicable.

## Non-Goals (for this ADR)

- Introducing DARTS as the primary LSTM backend.
- Introducing PyTorch Forecasting as a mandatory runtime dependency.
- Redesigning facade contracts beyond what is required to preserve existing LSTM output semantics.
- Broad model-selection architecture changes outside LSTM backend migration.

## Consequences

- Expected: improved dependency compatibility on newer Python/toolchain setups.
- Expected: no external contract break for consumers of LSTM forecast columns/index.
- Required follow-up: update tests and capability bridge assertions from TensorFlow-gated LSTM to torch-gated LSTM behavior.
