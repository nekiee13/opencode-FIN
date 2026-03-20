# Forecasting & Scenario Engine

## Overview

This repository contains the Phase-1 refactored Forecasting & Scenario Engine. The system supports multiple statistical, machine-learning, and hybrid forecasting models, optional exogenous regressors, and external worker processes for enrichment and model selection. The current development focus is **Path Stabilization**: converging execution paths, eliminating split-brain implementations, and locking behavior with contracts and tests.

---

## Phase-1 Refactor (Path Stabilization)

Phase-1 establishes non-negotiable architectural invariants before any deeper redesign. These rules define ownership, execution flow, and integration contracts, and must be satisfied before proceeding to later phases.

📄 **Authoritative specification:**

* [`docs/refactor/phase1_rules.md`](docs/refactor/phase1_rules.md)
* [`docs/refactor/decisions/0001-lstm-backend-pytorch-cutover.md`](docs/refactor/decisions/0001-lstm-backend-pytorch-cutover.md)
* [`docs/refactor/decisions/0002-dynamix-cpu-worker-integration.md`](docs/refactor/decisions/0002-dynamix-cpu-worker-integration.md)
* [`docs/followup_ml_runbook.md`](docs/followup_ml_runbook.md)

This document defines:

* `src/` as the **single source of truth** for all forecasting logic
* `compat/` as a **delegation-only adapter layer** for legacy entrypoints
* Structured **worker IPC** using JSON on `stdout` (diagnostics on `stderr`)
* `ForecastArtifact` as the **public execution contract** at the `src.models.facade` boundary
* Canonical ownership of models, adapters, workers, and contracts

Any refactor, bugfix, or feature added during Phase-1 must comply with these rules.

---

## Repository Layout (High-Level)

```
.
├── src/                 # Canonical implementations (models, facade, utils)
│   ├── models/          # All forecasting model logic (single source of truth)
│   ├── exo/             # Exogenous configuration and validation
│   ├── utils/           # Shared utilities (compat flags, worker protocol, etc.)
│   └── ui/              # Canonical UI components
│
├── compat/              # Thin adapters for legacy entrypoints (no algorithms)
│
├── scripts/
│   └── workers/         # External worker CLIs (JSON stdout protocol)
│
├── tests/               # Contract, snapshot, IPC, and regression tests
│
├── docs/
│   └── refactor/        # Phase-1 rules, decisions, and refactor documentation
│
└── tools/               # Audits, baselines, and developer utilities
```

---

## Development Rules (Phase-1)

* Do **not** add forecasting logic to `compat/`
* Do **not** parse human-readable `stdout` for control flow
* Do **not** introduce new model return types outside `ForecastArtifact`
* Prefer correctness, determinism, and debuggability over architectural novelty

Violations of these rules should fail CI.

---

## Runtime Dependency Notes

LSTM backend migration is torch-first in Phase-1.

* `requirements.txt` pins `torch==2.6.0` and `pytorch-forecasting==1.4.0`.
* Technical indicators use `TA-Lib==0.6.8`.
* TensorFlow/Keras, PyCaret, and Darts runtime pins were removed from project requirements.
* `xgboost` and `catboost` are not required by the current forecasting stack.
* Default install strategy is CPU-first from PyPI:

```bash
python -m pip install -r requirements.txt
```

For CUDA-enabled environments, install torch from the PyTorch CUDA wheel index that matches your driver/CUDA runtime, then install remaining dependencies:

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0
python -m pip install -r requirements.txt
```

### Optional: DynaMix Integration (CPU-Only)

FIN now includes an optional DynaMix forecast path (`DYNAMIX`) integrated through the canonical model layer.

- Canonical entrypoint: `src.models.dynamix.predict_dynamix`
- Worker entrypoint: `scripts/workers/dynamix_worker.py`
- Facade model key: `DYNAMIX`
- Runtime mode: forced CPU (`CUDA_VISIBLE_DEVICES=""` in worker)

Expected repository location for DynaMix:

```text
<FIN_ROOT>/vendor/DynaMix-python
```

Alternate supported location (also auto-discovered):

```text
<FIN_ROOT>/DynaMix-python
```

Override paths/interpreter with environment variables when needed:

- `FIN_DYNAMIX_REPO` - path to DynaMix-python checkout
- `FIN_DYNAMIX_PY_EXE` - python interpreter used by the DynaMix worker

`scripts/app3G.py` and `scripts/make_fh3_table.py` now auto-load a repo-root `.env` file (if present), so these can be persisted without shell `set` commands.

Example `.env`:

```env
FIN_DYNAMIX_REPO=F:\xPy\FIN-Git\opencode-FIN\DynaMix-python
FIN_DYNAMIX_PY_EXE=F:\vEnv\opencode-FIN\python.exe
```

Legacy/compat constants are available in `compat/Constants.py` under `DYNAMIX_*`.

### PyCaret Replacement and Model Capability Matrix

PyCaret is no longer part of the runtime stack.

- The legacy "PC" worker slot now runs a torch-based baseline worker (`scripts/workers/app3GPC.py`).
- In UI/table output this model is shown as `Torch` (internal columns remain `TorchForecast_*` for compatibility).
- `DYNAMIX` is integrated as a separate canonical model path via `src.models.dynamix`.

Current capability snapshot (app3G forecasting path):

| Model (table key) | Backend / entrypoint | Exogenous regressors | CI in table | Main tuning knobs |
|---|---|---|---|---|
| `Torch` | `scripts/workers/app3GPC.py` (pytorch-forecasting Baseline) | No | Yes (`TorchForecast_Lower/Upper`) | `FIN_TF_COVERAGE`, `FIN_FH` |
| `DYNAMIX` | `src.models.dynamix.predict_dynamix` + worker | No | Columns exist, often unavailable (`-`) | `DYNAMIX_*` constants / env overrides |
| `ARIMAX` | `src.models.arimax` (with fallback path in compat API) | Yes | Yes | `ARIMA_MAX_P/Q/D`, `ARIMA_SEASONAL`, PI knobs |
| `PCE` | `src.models.pce_narx` (or worker fallback) | Yes | Yes | `PCE_*` knobs (lags/degree/samples/lasso), `PCE_PI_WIDTH_MULT` |
| `LSTM` | `src.models.lstm` (torch) | Yes | Yes | `LSTM_LOOKBACK`, `LSTM_EPOCHS`, `LSTM_QUANTILES`, `LSTM_PI_WIDTH_MULT` |
| `GARCH` | compat API (`arch`) | Yes | No (point forecast only in table) | PI does not currently surface for GARCH in app table |
| `VAR` | compat API (`statsmodels`) | No (uses endogenous multivariate inputs) | No | `VAR_MAX_LAGS` |
| `RW` | `src.models.random_walk` | No | No | `RW_DRIFT_ENABLED` |
| `ETS` | `src.models.ets` | No | No | `ETS_TREND`, `ETS_SEASONAL`, `ETS_SEASONAL_PERIODS` |

### Predictive Interval Harmonization (ARIMAX, PCE, LSTM)

FIN harmonizes these models to a shared predictive-interval target:

- Central coverage: `86%`
- Quantiles: `q_low=0.07`, `q_high=0.93`
- Alpha: `0.14`

Configuration knobs live in `compat/Constants.py`:

- `PI_COVERAGE`, `PI_ALPHA`, `PI_Q_LOW`, `PI_Q_HIGH`
- `PI_CALIBRATION_ENABLED`, `PI_CALIBRATION_MIN_SAMPLES`
- `PCE_PI_WIDTH_MULT`, `LSTM_PI_WIDTH_MULT` (model-specific width controls)

Lightweight residual-quantile calibration can be enabled globally to widen intervals consistently across models.

When running `app3G`, DynaMix is executed twice:

- Run 1: `standardize=True, fit_nonstationary=False`
- Run 2: `standardize=True, fit_nonstationary=True`

The forecast table shows both DynaMix values in a single cell (`<br>` separated).

---

## Status

* Phase-1: **In progress** (Path Stabilization)
* Later phases (registries, plugin systems, behavioral ABCs) are explicitly out of scope until Phase-1 is complete.

---

## License / Usage

(Define as appropriate for your project)
## Trunk Workflow Policy
- trunk-only workflow is active.
- direct development on main is required.
- no routine feature branches are allowed.
- active runtime: oc-fin-opencode.
- paused runtime: oc-fin.
