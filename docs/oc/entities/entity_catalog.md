# OC Entity Catalog

Generated at: 2026-04-11T14:52:28+00:00

## Python Dataclasses

### CheckResult
Source: `tools/hello-stack/check_stack.py:13`

| Field | Type | Default |
| --- | --- | --- |
| `name` | `str` | no |
| `status` | `str` | no |
| `detail` | `str` | no |

## TypeScript Interfaces

| Interface | Fields | Source |
| --- | ---: | --- |
| `UserData` | 2 | `vendor/OpenAgentsControl/evals/framework/src/__tests__/error-handling.test.ts` |
| `ValidationResult` | 2 | `vendor/OpenAgentsControl/evals/framework/src/__tests__/error-handling.test.ts` |
| `Violation` | 3 | `vendor/OpenAgentsControl/evals/framework/src/__tests__/error-handling.test.ts` |
| `AgentMetadata` | 8 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/agent-model-evaluator.ts` |
| `AgentModelExpectations` | 3 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/agent-model-evaluator.ts` |
| `CodeAnalysis` | 6 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/error-handling-evaluator.ts` |
| `ErrorMessage` | 3 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/error-handling-evaluator.ts` |
| `RiskyOperation` | 4 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/error-handling-evaluator.ts` |
| `AggregatedResult` | 10 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/evaluator-runner.ts` |
| `RunnerConfig` | 4 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/evaluator-runner.ts` |
| `PerformanceMetrics` | 7 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/performance-metrics-evaluator.ts` |
| `ToolLatencyStats` | 5 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/performance-metrics-evaluator.ts` |
| `WorkflowStep` | 3 | `vendor/OpenAgentsControl/evals/framework/src/evaluators/report-first-evaluator.ts` |
| `DelegationEvent` | 7 | `vendor/OpenAgentsControl/evals/framework/src/logging/types.ts` |
| `LogEntry` | 6 | `vendor/OpenAgentsControl/evals/framework/src/logging/types.ts` |
| `SessionNode` | 7 | `vendor/OpenAgentsControl/evals/framework/src/logging/types.ts` |
| `SessionTree` | 4 | `vendor/OpenAgentsControl/evals/framework/src/logging/types.ts` |
| `ApprovalDecision` | 2 | `vendor/OpenAgentsControl/evals/framework/src/sdk/approval/approval-strategy.ts` |
| `ApprovalStrategy` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/approval/approval-strategy.ts` |
| `SmartApprovalConfig` | 6 | `vendor/OpenAgentsControl/evals/framework/src/sdk/approval/smart-approval-strategy.ts` |
| `ClientConfig` | 2 | `vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts` |
| `PromptConfig` | 4 | `vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts` |
| `SessionConfig` | 1 | `vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts` |
| `SessionInfo` | 4 | `vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts` |
| `PermissionRequestEvent` | 6 | `vendor/OpenAgentsControl/evals/framework/src/sdk/event-stream-handler.ts` |
| `ServerEvent` | 3 | `vendor/OpenAgentsControl/evals/framework/src/sdk/event-stream-handler.ts` |
| `ModelBehavior` | 4 | `vendor/OpenAgentsControl/evals/framework/src/sdk/model-behaviors.ts` |
| `PromptMetadata` | 6 | `vendor/OpenAgentsControl/evals/framework/src/sdk/prompt-manager.ts` |
| `SwitchResult` | 6 | `vendor/OpenAgentsControl/evals/framework/src/sdk/prompt-manager.ts` |
| `CategorySummary` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `CompactTestResult` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `PackageJson` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `ResultMetadata` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `ResultSummary` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `SaveOptions` | 3 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `TestSummary` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `ViolationDetail` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `ValidationLogger` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-validator.ts` |
| `CliArgs` | 12 | `vendor/OpenAgentsControl/evals/framework/src/sdk/run-sdk-tests.ts` |
| `ServerConfig` | 8 | `vendor/OpenAgentsControl/evals/framework/src/sdk/server-manager.ts` |
| `ValidationError` | 3 | `vendor/OpenAgentsControl/evals/framework/src/sdk/suite-validator.ts` |
| `ValidationResult` | 5 | `vendor/OpenAgentsControl/evals/framework/src/sdk/suite-validator.ts` |
| `ExecutionConfig` | 4 | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-executor.ts` |
| `ExecutionLogger` | 0 | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-executor.ts` |
| `ExecutionResult` | 5 | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-executor.ts` |
| `TestResult` | 9 | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-runner.ts` |
| `TestRunnerConfig` | 6 | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-runner.ts` |
| `ValidationStats` | 5 | `vendor/OpenAgentsControl/evals/framework/src/sdk/validate-suites-cli.ts` |
| `ApprovalGateCheck` | 9 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `Check` | 4 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `ContextLoadingCheck` | 9 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `DelegationCheck` | 5 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `EvaluationResult` | 6 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `EvaluatorConfig` | 3 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `EvaluatorRegistry` | 0 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `Evidence` | 4 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `ExpectedBehavior` | 9 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `FrameworkConfig` | 4 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `IEvaluator` | 2 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `Message` | 10 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `MessageMetrics` | 3 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `MessageWithParts` | 2 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `ModelInfo` | 2 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `Part` | 6 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `SessionInfo` | 5 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `TaskContext` | 3 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `TestCase` | 8 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `TestResult` | 12 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `TestSuite` | 8 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `TimelineEvent` | 7 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `TokenUsage` | 3 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `ToolUsageCheck` | 5 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `Violation` | 5 | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |
| `AbilityListItem` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/loader/index.ts` |
| `ChatMessageOutput` | 1 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `EventInput` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `OpencodeClient` | 1 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `PluginConfig` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `PluginContext` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `SessionIdleOutput` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `ToolExecuteInput` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `ToolExecuteOutput` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `AbilitiesSDKOptions` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/sdk.ts` |
| `AbilityInfo` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/sdk.ts` |
| `ExecutionResult` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/sdk.ts` |
| `Ability` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `AbilityExecution` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `ExecutorContext` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `InputDefinition` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `LoadedAbility` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `LoaderOptions` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `ScriptStep` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `StepResult` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `ValidationError` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |
| `ValidationResult` | 0 | `vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts` |

## TypeScript Type Aliases

| Type | Source |
| --- | --- |
| `Severity` | `vendor/OpenAgentsControl/evals/framework/src/__tests__/error-handling.test.ts` |
| `OpencodeClient` | `vendor/OpenAgentsControl/evals/framework/src/collector/session-reader.ts` |
| `TextPartInput` | `vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts` |
| `EventHandler` | `vendor/OpenAgentsControl/evals/framework/src/sdk/event-stream-handler.ts` |
| `EventType` | `vendor/OpenAgentsControl/evals/framework/src/sdk/event-stream-handler.ts` |
| `PermissionHandler` | `vendor/OpenAgentsControl/evals/framework/src/sdk/event-stream-handler.ts` |
| `TestCategory` | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `ViolationSeverity` | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `TestDefinition` | `vendor/OpenAgentsControl/evals/framework/src/sdk/suite-validator.ts` |
| `TestSuite` | `vendor/OpenAgentsControl/evals/framework/src/sdk/suite-validator.ts` |
| `ApprovalStrategyConfig` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-case-schema.ts` |
| `BehaviorExpectation` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-case-schema.ts` |
| `ExpectedResults` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-case-schema.ts` |
| `ExpectedViolation` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-case-schema.ts` |
| `MultiMessage` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-case-schema.ts` |
| `TestCase` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-case-schema.ts` |
| `TestSuite` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-case-schema.ts` |
| `TaskType` | `vendor/OpenAgentsControl/evals/framework/src/types/index.ts` |

## TypeScript Classes

| Class | Extends | Implements | Source |
| --- | --- | --- | --- |
| `MessageParser` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/collector/message-parser.ts` |
| `SessionReader` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/collector/session-reader.ts` |
| `TimelineBuilder` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/collector/timeline-builder.ts` |
| `AgentModelEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/agent-model-evaluator.ts` |
| `ApprovalGateEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/approval-gate-evaluator.ts` |
| `BaseEvaluator` | `-` | `IEvaluator` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/base-evaluator.ts` |
| `BehaviorEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/behavior-evaluator.ts` |
| `CleanupConfirmationEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/cleanup-confirmation-evaluator.ts` |
| `ContextLoadingEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/context-loading-evaluator.ts` |
| `DelegationEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/delegation-evaluator.ts` |
| `ErrorHandlingEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/error-handling-evaluator.ts` |
| `EvaluatorRunner` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/evaluator-runner.ts` |
| `ExecutionBalanceEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/execution-balance-evaluator.ts` |
| `PerformanceMetricsEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/performance-metrics-evaluator.ts` |
| `ReportFirstEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/report-first-evaluator.ts` |
| `StopOnFailureEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/stop-on-failure-evaluator.ts` |
| `ToolUsageEvaluator` | `BaseEvaluator` | `-` | `vendor/OpenAgentsControl/evals/framework/src/evaluators/tool-usage-evaluator.ts` |
| `MultiAgentLogger` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/logging/logger.ts` |
| `SessionTracker` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/logging/session-tracker.ts` |
| `AutoApproveStrategy` | `-` | `ApprovalStrategy` | `vendor/OpenAgentsControl/evals/framework/src/sdk/approval/auto-approve-strategy.ts` |
| `AutoDenyStrategy` | `-` | `ApprovalStrategy` | `vendor/OpenAgentsControl/evals/framework/src/sdk/approval/auto-deny-strategy.ts` |
| `SmartApprovalStrategy` | `-` | `ApprovalStrategy` | `vendor/OpenAgentsControl/evals/framework/src/sdk/approval/smart-approval-strategy.ts` |
| `ClientManager` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts` |
| `EventStreamHandler` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/event-stream-handler.ts` |
| `PromptManager` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/prompt-manager.ts` |
| `ResultSaver` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts` |
| `ResultValidator` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/result-validator.ts` |
| `ServerManager` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/server-manager.ts` |
| `SuiteValidator` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/suite-validator.ts` |
| `TestExecutor` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-executor.ts` |
| `TestRunner` | `-` | `-` | `vendor/OpenAgentsControl/evals/framework/src/sdk/test-runner.ts` |
| `ExecutionManager` | `-` | `-` | `vendor/OpenAgentsControl/packages/plugin-abilities/src/executor/execution-manager.ts` |
| `AbilitiesPlugin` | `-` | `-` | `vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts` |
| `AbilitiesSDK` | `-` | `-` | `vendor/OpenAgentsControl/packages/plugin-abilities/src/sdk.ts` |

