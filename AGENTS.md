# AGENTS.md
Repository instructions for autonomous coding agents.

## Quick Start (5-6 commands)
```bash
python -m pip install -r requirements.txt
python -m pytest
python -m pytest tests/test_infra.py::test_import_loading_module
python -m pytest --run-cpi -m cpi
python -m ruff check src compat scripts tests tools
python scripts/app3G.py --help
```

## Project Context
- Project: Forecasting and Scenario Engine.
- Current phase: Path Stabilization (Phase-1).
- Canonical implementation belongs in `src/`.
- `compat/` is a thin adapter layer only.
- Public forecast boundary uses `src.models.facade.ForecastArtifact`.
- Prioritize deterministic behavior and stable contracts.

Primary references:
- `README.md`
- `docs/refactor/phase1_rules.md`

## Repository Layout
- `src/models/`: canonical forecasting models and facade.
- `src/data/`: canonical CSV loading and normalization.
- `src/exo/`: exogenous config and validation.
- `src/structural/`: SVL/TDA structural indicators.
- `src/utils/`: compatibility flags, pivots, temp/debug helpers.
- `src/ui/`: canonical GUI layer.
- `compat/`: legacy module/API shims (delegation only).
- `scripts/`: runnable entrypoints and exporters.
- `scripts/workers/`: worker CLIs.
- `tools/`: ownership map, import audit, baselines.
- `tests/`: smoke, snapshot, contract, and policy tests.

## Setup Commands
Use your active Python environment.

Install dependencies:
```bash
python -m pip install -r requirements.txt
```

Notes:
- `pyproject.toml` is currently empty.
- `pytest.ini` defines default pytest behavior.
- Optional deterministic pin used by tests: `python -m pip install -c constraints-test.txt setuptools==80.10.2`

## Build and Run Commands
No formal package build step is configured; verification is test-driven.

Entrypoint commands:
```bash
python app3G.py --help
python scripts/app3G.py --help
python scripts/svl_export.py --help
python scripts/tda_export.py --help
python scripts/make_fh3_table.py
```

Utility commands:
```bash
python tools/ownership_map.py
python tools/import_audit.py
python tools/import_audit.py --static-only
```

## Test Commands (including single-test)
Run full suite:
```bash
python -m pytest
```

Run one test file:
```bash
python -m pytest tests/test_infra.py
```

Run one test function:
```bash
python -m pytest tests/test_infra.py::test_import_loading_module
```

Run by keyword:
```bash
python -m pytest -k "compat_import_hygiene"
```

Run CPI acceptance tests (opt-in):
```bash
python -m pytest --run-cpi -m cpi
```

Run one CPI acceptance test:
```bash
python -m pytest --run-cpi tests/test_part3_structural_exporters_acceptance.py::test_svl_export_writes_artifacts_and_uses_global_min_asof
```

Important guardrail tests:
- `tests/test_compat_import_hygiene.py`
- `tests/test_compat_thinness_shape.py`
- `tests/test_facade_import_smoke.py`
- `tests/test_entrypoints_smoke.py`

## Lint, Format, and Type Guidance
No enforced lint/type config is checked in (`setup.cfg`, `tox.ini`, etc. absent).
`ruff` is present in dependencies, so use targeted checks.

Recommended lint command:
```bash
python -m ruff check src compat scripts tests tools
```

Formatting policy:
- Do not run broad repo-wide formatting sweeps during Phase-1.
- Keep edits minimal and localized to task scope.
- Preserve surrounding file style and section structure.

Type policy:
- Keep function signatures annotated.
- Use explicit pandas index coercion/validation where needed.
- Use `cast(...)` where static typing around pandas needs narrowing.

## Code Style Conventions
- Imports: include `from __future__ import annotations`; group imports as stdlib, third-party, local.
- Optional dependencies: keep heavy imports gated or local to execution paths.
- Static typing: use `TYPE_CHECKING` for static-only imports where useful.
- Naming: `snake_case` for funcs/vars, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Compatibility naming: preserve legacy names only when adapter stability requires it.
- Boundary checks: validate shape/index/required columns on external boundaries.
- Forecast contract: keep canonical outputs normalized to `ForecastArtifact`.
- Structured contracts: prefer dataclasses for cross-module data structures.
- Errors: fail fast on invariants in canonical layers.
- Degradation: in optional-dependency paths, return deterministic fallbacks and log warnings.
- Exception scope: catch broad exceptions primarily at boundaries/adapters/workers.
- Logging: include ticker/model/path context when available.
- Compat rule: do not add forecasting algorithms to `compat/`.
- Compat thinness: keep compat functions as delegation plus minimal argument adaptation.
- Compat imports: avoid direct heavy model-library imports in `compat/`.
- Entrypoints: keep scripts runnable from repo root and robust to current working directory.
- Workers: prefer deterministic machine-readable outputs and avoid fragile stdout parsing.

## Completion Checklist for Agents
- Keep business logic changes in `src/`.
- Maintain `compat/` as delegation-only.
- Run targeted tests for touched areas.
- Run guardrail tests when touching contracts/adapters/import behavior.
- Run targeted lint checks for changed modules.
- Update docs/tests when contract or behavior changes are intentional.

## Cursor and Copilot Rules
Checked locations:
- `.cursor/rules/`
- `.cursorrules`
- `.github/copilot-instructions.md`

Result:
- No Cursor rules or Copilot instruction files were found in this repo.
