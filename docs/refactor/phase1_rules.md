# Phase 1 Rules (Path Stabilization)

This document defines the **Phase-1 invariants** for the FIN refactor. During Phase 1, the priority is **behavioral correctness and entrypoint continuity** while the codebase converges to a single canonical implementation.

## 1) Objectives (Phase 1)

1. **Single-source-of-truth convergence**: all forecasting/modeling logic must converge into `src/`.
2. **Compatibility continuity**: legacy entrypoints (scripts and GUI) remain runnable while routing through canonical `src/` logic.
3. **Deterministic interfaces**: model execution returns a standardized artifact contract, and worker IPC uses a structured protocol.

## 2) Non-goals (explicitly deferred)

The following are **out of scope** for Phase 1 unless required for correctness:

- Re-architecting with complex plugin systems or dependency injection.
- Introducing extensive abstract base classes or formal interface hierarchies beyond what is needed to enforce contracts.
- Large-scale code formatting / re-linting that increases merge conflicts.

## 3) Phase-1 invariants (must hold for every PR)

### 3.1 Canonical code ownership

- **`src/` is canonical** for:
  - forecasting logic, model implementations, artifact normalization
  - exogenous regressor handling (`src/exo`)
  - structural context computation (`src/structural`)
  - shared utilities (`src/utils`)

- **`compat/` is a shim only**:
  - may adapt legacy function signatures
  - may re-export modules/classes
  - **must not** contain algorithmic re-implementations of forecasting/modeling logic

- **`scripts/` are entrypoints**:
  - may call into `src/` or `compat/`
  - must not become canonical “business logic” repositories

### 3.2 Output contract: `ForecastArtifact`

- All **public** model execution entrypoints exposed via `src.models.facade` must return **`ForecastArtifact`**.
- Downstream consumers (GUI, scripts, legacy adapters) should treat `ForecastArtifact` as the stable interface.
- Model-specific internal return types are permitted only **below** the facade boundary.

**Minimum `ForecastArtifact` expectations (Phase 1):**

- contains a `pred_df` with a `DatetimeIndex`
- the declared prediction column exists (`pred_col`)
- artifacts are valid for the forecast horizon index used by consumers

### 3.3 Worker IPC: structured protocol only

Workers **must not** communicate results via “human text” intended to be parsed.

**Rule:**
- Worker **stdout** emits exactly one terminal payload line: a JSON object.
- Worker **stderr** carries diagnostics (logs, warnings, progress, tracebacks).

**Required JSON envelope fields (Phase 1):**

- `protocol_version` (integer)
- `ok` (boolean)
- on success: `artifact_csv` (string path) and optional `meta` (object)
- on failure: `error` object with at least `{ "type": str, "message": str }`

### 3.4 Entrypoint continuity

- Root scripts and GUI entrypoints must remain runnable during Phase 1.
- Where behavior changes are unavoidable (e.g., canonicalizing a model implementation), changes must be:
  - explicitly documented in a decision record under `docs/refactor/decisions/`
  - locked with snapshot tests or golden baselines

### 3.5 Optional dependency gating

- Optional model stacks (e.g., deep learning, heavy statistical libraries) must degrade gracefully.
- Dependency detection must be centralized (prefer `src/utils/compat.py`).
- Missing optional dependencies must produce deterministic outcomes:
  - either a controlled failure artifact, or
  - a typed exception that the facade converts into a failure artifact

## 4) Canonical ownership map

This section defines **what “owns” what** in Phase 1.

### 4.1 `src/` ownership

| Path | Ownership | Notes |
|---|---|---|
| `src/models/*` | Canonical implementations | All model logic, normalization, and model-specific execution lives here. |
| `src/models/facade.py` | Canonical boundary | The **public execution surface**. Must return `ForecastArtifact`. |
| `src/exo/*` | Canonical exogenous handling | Configuration, validation, and scenario handling (as implemented). |
| `src/structural/*` | Canonical structural indicators | SVL/TDA computations and exportable context generation. |
| `src/data/*` | Canonical data loading | Centralized load + transformation logic. |
| `src/utils/*` | Canonical utilities | Capability gating, pivot logic, and shared helpers. |
| `src/ui/*` | Canonical UI | New UI implementation; legacy UI may route through compat. |

### 4.2 `compat/` ownership

| Path | Ownership | Notes |
|---|---|---|
| `compat/*.py` | Adapter/shim only | Preserve legacy module names and signatures while delegating into `src/`. |
| `compat/Models.py` | Delegation only | Must not import modeling libs directly. Calls into `src.models.facade`. |
| `compat/GUI.py` | Delegation only | May keep Tk wiring, but logic must route to `src/ui` and `src/models.facade`. |

**Hard rule:** no parallel algorithmic implementations in `compat/`.

### 4.3 `scripts/` and workers ownership

| Path | Ownership | Notes |
|---|---|---|
| `scripts/*.py` | Runnable entrypoints | Thin orchestration and argument parsing; call into `src/`. |
| `scripts/workers/*.py` | CLI workers | Implement CLI behavior and data plumbing, not parsing contracts. |

Workers own how they compute outputs, but **do not own** the protocol contract. The protocol is owned by `src` utilities.

## 5) Enforcement (how these rules stay true)

Phase 1 requires guardrails so refactors can proceed aggressively without regressions.

### 5.1 Guardrail tests (minimum)

- **Compat import hygiene**: fails if `compat/` imports forbidden modeling libraries.
- **Compat thinness**: fails if `compat/` contains large algorithmic functions.
- **Facade contract**: parameterized tests asserting every facade entrypoint returns `ForecastArtifact`.
- **Worker protocol tests**: unit tests for protocol parsing + subprocess integration tests.

### 5.2 Change management

- Any intentional output drift must be:
  - documented in a decision record
  - locked with a snapshot update (deliberate, reviewed change)

## 6) How to interpret conflicts

When this document conflicts with convenience or legacy behavior:

1. **Correctness and determinism win** (single codepath, stable contract).
2. **Entrypoint continuity wins over purity** (thin shims are allowed in Phase 1).
3. **Phase-2 architecture work is deferred** unless required for Phase-1 correctness.
