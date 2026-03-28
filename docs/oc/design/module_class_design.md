# Module and Class Design

## Folder Structure and Responsibilities

| Folder | Responsibility | Evidence |
| --- | --- | --- |
| `.opencode/` | Active OC runtime entrypoint, plugin list, MCP wiring, and symlink bridge to vendored OAC payload | `.opencode/opencode.json`, `docs/integration-pilot/epic-2-oac-path-integrity-check.md` |
| `tools/hello-stack/` | Minimal stack bootstrap templates and executable stack health checks | `tools/hello-stack/check_stack.py`, `tools/hello-stack/quickstart.md` |
| `docs/integration-pilot/` | Pilot run evidence, ADRs, validation logs, and decision notes | `docs/integration-pilot/epic-4-hello-stack-run.md` |
| `vendor/OpenAgentsControl/.opencode/` | Vendored OAC payload: agents, commands, context, tools, skills, and prompts | `vendor/OpenAgentsControl/.opencode/` |
| `vendor/OpenAgentsControl/packages/plugin-abilities/src/` | Ability runtime implementation: loader, validator, executor, plugin integration, SDK | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `vendor/OpenAgentsControl/evals/framework/src/` | Evaluation runtime: collectors, evaluators, session tracking, test execution, result persistence | `vendor/OpenAgentsControl/evals/framework/src/evaluators/` |

## Scope Metrics

Source: `docs/oc/generated/oc_inventory.json`

- In-scope file count: 440
- Extension mix: `.md` 303, `.ts` 90, `.json` 29, `.yaml` 9, `.sh` 8, `.py` 1
- Effective first-party runtime files in `.opencode`: 4 configuration files (excluding `node_modules`)

## Key Module Design

### 1) Runtime Configuration Module

- Primary object: OpenCode runtime config in `.opencode/opencode.json`
- Input responsibility: plugin and MCP endpoint declarations
- Output responsibility: active runtime behavior for retrieval, skills, and editing tools

### 2) Stack Validation Module

- Primary object: `tools/hello-stack/check_stack.py`
- Key type: `CheckResult` dataclass
- Responsibility: deterministic checks for binary availability, MCP launcher readiness, and symlink integrity

### 3) Ability Execution Module

- Primary objects: `AbilitiesPlugin`, `AbilitiesSDK`, `ExecutionManager`
- Responsibility split:
  - loader resolves ability definitions
  - validator enforces ability and input schema
  - executor runs script-step workflow and result formatting
  - plugin layer injects runtime constraints and tool enforcement

### 4) Evaluation Module

- Primary objects: `BaseEvaluator` and evaluator subclasses, `EvaluatorRunner`, `SessionReader`, `TimelineBuilder`
- Responsibility: evaluate behavioral constraints, approval gating, delegation, and performance quality

## Class Design Summary

Source: `docs/oc/generated/oc_class_index.json`

- Python classes: 1
- Python dataclasses: 1
- TypeScript classes: 34
- TypeScript interfaces: 103
- TypeScript type aliases: 18

## Class Responsibility Highlights

| Class | Responsibility | Source |
| --- | --- | --- |
| `CheckResult` | Carries stack check status (`name`, `status`, `detail`) | `tools/hello-stack/check_stack.py:13` |
| `AbilitiesPlugin` | Runtime ability orchestration and tool gating hooks | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `AbilitiesSDK` | Programmatic API for listing, validating, and executing abilities | `vendor/OpenAgentsControl/packages/plugin-abilities/src/sdk.ts` |
| `ExecutionManager` | Single active ability execution lifecycle management | `vendor/OpenAgentsControl/packages/plugin-abilities/src/executor/execution-manager.ts` |
| `BaseEvaluator` | Shared evaluator contract implementation base | `vendor/OpenAgentsControl/evals/framework/src/evaluators/base-evaluator.ts` |
| `EvaluatorRunner` | Aggregates evaluator outputs for each session | `vendor/OpenAgentsControl/evals/framework/src/evaluators/evaluator-runner.ts` |

## Full Entity Listing

- Human-readable index: `docs/oc/entities/entity_catalog.md`
- Dataclass mirrors: `docs/oc/entities/entity_dataclasses.py`
