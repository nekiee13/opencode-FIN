# Forecasting & Scenario Engine

## Overview

This repository contains the Phase-1 refactored Forecasting & Scenario Engine. The system supports multiple statistical, machine-learning, and hybrid forecasting models, optional exogenous regressors, and external worker processes for enrichment and model selection. The current development focus is **Path Stabilization**: converging execution paths, eliminating split-brain implementations, and locking behavior with contracts and tests.

---

## Phase-1 Refactor (Path Stabilization)

Phase-1 establishes non-negotiable architectural invariants before any deeper redesign. These rules define ownership, execution flow, and integration contracts, and must be satisfied before proceeding to later phases.

📄 **Authoritative specification:**

* [`docs/refactor/phase1_rules.md`](docs/refactor/phase1_rules.md)
* [`docs/refactor/decisions/0001-lstm-backend-pytorch-cutover.md`](docs/refactor/decisions/0001-lstm-backend-pytorch-cutover.md)

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

* `requirements.txt` and `requirements.test.txt` pin `torch==2.6.0`.
* TensorFlow/Keras runtime pins were removed from the project requirements.
* Default install strategy is CPU-first from PyPI:

```bash
python -m pip install -r requirements.txt
```

For CUDA-enabled environments, install torch from the PyTorch CUDA wheel index that matches your driver/CUDA runtime, then install remaining dependencies:

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0
python -m pip install -r requirements.txt
```

---

## Status

* Phase-1: **In progress** (Path Stabilization)
* Later phases (registries, plugin systems, behavioral ABCs) are explicitly out of scope until Phase-1 is complete.

---

## License / Usage

(Define as appropriate for your project)
