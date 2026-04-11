from __future__ import annotations

from dataclasses import dataclass
from typing import Any

"""Generated OC entity dataclasses.

Each dataclass mirrors an entity discovered in OC scope.
TypeScript entities are mapped to Any for portability.
"""

@dataclass
class CheckResult:
    """Source: tools/hello-stack/check_stack.py:13"""
    name: str
    status: str
    detail: str

@dataclass
class UserDataErrorHandlingTest:
    """Source: vendor/OpenAgentsControl/evals/framework/src/__tests__/error-handling.test.ts"""
    email: Any = None
    age: Any = None

@dataclass
class ValidationResultErrorHandlingTest:
    """Source: vendor/OpenAgentsControl/evals/framework/src/__tests__/error-handling.test.ts"""
    isValid: Any = None
    errors: Any = None

@dataclass
class ViolationErrorHandlingTest:
    """Source: vendor/OpenAgentsControl/evals/framework/src/__tests__/error-handling.test.ts"""
    type: Any = None
    severity: Any = None
    message: Any = None

@dataclass
class AgentMetadataAgentModelEvaluator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/agent-model-evaluator.ts"""
    id: Any = None
    name: Any = None
    description: Any = None
    category: Any = None
    type: Any = None
    version: Any = None
    mode: Any = None
    promptSnippet: Any = None

@dataclass
class AgentModelExpectationsAgentModelEvaluator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/agent-model-evaluator.ts"""
    expectedAgent: Any = None
    expectedModel: Any = None
    projectPath: Any = None

@dataclass
class CodeAnalysisErrorHandlingEvaluator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/error-handling-evaluator.ts"""
    filePath: Any = None
    content: Any = None
    language: Any = None
    riskyOperations: Any = None
    errorMessages: Any = None
    hasErrorBoundaries: Any = None

@dataclass
class ErrorMessageErrorHandlingEvaluator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/error-handling-evaluator.ts"""
    line: Any = None
    message: Any = None
    isGeneric: Any = None

@dataclass
class RiskyOperationErrorHandlingEvaluator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/error-handling-evaluator.ts"""
    type: Any = None
    line: Any = None
    code: Any = None
    hasErrorHandling: Any = None

@dataclass
class AggregatedResultEvaluatorRunner:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/evaluator-runner.ts"""
    sessionId: Any = None
    sessionInfo: Any = None
    timestamp: Any = None
    evaluatorResults: Any = None
    overallPassed: Any = None
    overallScore: Any = None
    totalViolations: Any = None
    violationsBySeverity: Any = None
    warning: Any = None
    info: Any = None

@dataclass
class RunnerConfigEvaluatorRunner:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/evaluator-runner.ts"""
    sessionReader: Any = None
    timelineBuilder: Any = None
    evaluators: Any = None
    sdkClient: Any = None

@dataclass
class PerformanceMetricsPerformanceMetricsEvaluator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/performance-metrics-evaluator.ts"""
    total_duration_ms: Any = None
    tool_latencies_ms: Any = None
    inference_time_ms: Any = None
    idle_time_ms: Any = None
    event_distribution: Any = None
    tool_count: Any = None
    message_count: Any = None

@dataclass
class ToolLatencyStatsPerformanceMetricsEvaluator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/performance-metrics-evaluator.ts"""
    count: Any = None
    avg_ms: Any = None
    min_ms: Any = None
    max_ms: Any = None
    total_ms: Any = None

@dataclass
class WorkflowStepReportFirstEvaluator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/evaluators/report-first-evaluator.ts"""
    step: Any = None
    timestamp: Any = None
    evidence: Any = None

@dataclass
class DelegationEventTypes:
    """Source: vendor/OpenAgentsControl/evals/framework/src/logging/types.ts"""
    id: Any = None
    timestamp: Any = None
    parentSessionId: Any = None
    childSessionId: Any = None
    fromAgent: Any = None
    toAgent: Any = None
    prompt: Any = None

@dataclass
class LogEntryTypes:
    """Source: vendor/OpenAgentsControl/evals/framework/src/logging/types.ts"""
    timestamp: Any = None
    sessionId: Any = None
    depth: Any = None
    type: Any = None
    content: Any = None
    metadata: Any = None

@dataclass
class SessionNodeTypes:
    """Source: vendor/OpenAgentsControl/evals/framework/src/logging/types.ts"""
    sessionId: Any = None
    parentId: Any = None
    agent: Any = None
    depth: Any = None
    startTime: Any = None
    endTime: Any = None
    children: Any = None

@dataclass
class SessionTreeTypes:
    """Source: vendor/OpenAgentsControl/evals/framework/src/logging/types.ts"""
    root: Any = None
    totalSessions: Any = None
    maxDepth: Any = None
    delegations: Any = None

@dataclass
class ApprovalDecisionApprovalStrategy:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/approval/approval-strategy.ts"""
    approved: Any = None
    reason: Any = None

@dataclass
class ApprovalStrategyApprovalStrategy:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/approval/approval-strategy.ts"""
    data: Any = None

@dataclass
class SmartApprovalConfigSmartApprovalStrategy:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/approval/smart-approval-strategy.ts"""
    allowedTools: Any = None
    deniedTools: Any = None
    approvePatterns: Any = None
    denyPatterns: Any = None
    maxApprovals: Any = None
    defaultDecision: Any = None

@dataclass
class ClientConfigClientManager:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts"""
    baseUrl: Any = None
    timeout: Any = None

@dataclass
class PromptConfigClientManager:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts"""
    text: Any = None
    agent: Any = None
    model: Any = None
    modelID: Any = None

@dataclass
class SessionConfigClientManager:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts"""
    title: Any = None

@dataclass
class SessionInfoClientManager:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/client-manager.ts"""
    id: Any = None
    title: Any = None
    messages: Any = None
    parts: Any = None

@dataclass
class PermissionRequestEventEventStreamHandler:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/event-stream-handler.ts"""
    type: Any = None
    properties: Any = None
    permissionId: Any = None
    message: Any = None
    tool: Any = None
    args: Any = None

@dataclass
class ServerEventEventStreamHandler:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/event-stream-handler.ts"""
    type: Any = None
    properties: Any = None
    timestamp: Any = None

@dataclass
class ModelBehaviorModelBehaviors:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/model-behaviors.ts"""
    sendsCompletionText: Any = None
    mayEndWithToolCalls: Any = None
    typicalResponseTime: Any = None
    toolCompletionGrace: Any = None

@dataclass
class PromptMetadataPromptManager:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/prompt-manager.ts"""
    model_family: Any = None
    recommended_models: Any = None
    tested_with: Any = None
    last_tested: Any = None
    maintainer: Any = None
    status: Any = None

@dataclass
class SwitchResultPromptManager:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/prompt-manager.ts"""
    success: Any = None
    variantPath: Any = None
    agentPath: Any = None
    metadata: Any = None
    recommendedModel: Any = None
    error: Any = None

@dataclass
class CategorySummaryResultSaver:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts"""
    data: Any = None

@dataclass
class CompactTestResultResultSaver:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts"""
    data: Any = None

@dataclass
class PackageJsonResultSaver:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts"""
    data: Any = None

@dataclass
class ResultMetadataResultSaver:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts"""
    data: Any = None

@dataclass
class ResultSummaryResultSaver:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts"""
    data: Any = None

@dataclass
class SaveOptionsResultSaver:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts"""
    promptVariant: Any = None
    modelFamily: Any = None
    promptsDir: Any = None

@dataclass
class TestSummaryResultSaver:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts"""
    data: Any = None

@dataclass
class ViolationDetailResultSaver:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-saver.ts"""
    data: Any = None

@dataclass
class ValidationLoggerResultValidator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/result-validator.ts"""
    data: Any = None

@dataclass
class CliArgsRunSdkTests:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/run-sdk-tests.ts"""
    debug: Any = None
    verbose: Any = None
    noEvaluators: Any = None
    core: Any = None
    suite: Any = None
    agent: Any = None
    pattern: Any = None
    timeout: Any = None
    model: Any = None
    promptVariant: Any = None
    subagent: Any = None
    delegate: Any = None

@dataclass
class ServerConfigServerManager:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/server-manager.ts"""
    port: Any = None
    hostname: Any = None
    printLogs: Any = None
    logLevel: Any = None
    timeout: Any = None
    cwd: Any = None
    debug: Any = None
    agent: Any = None

@dataclass
class ValidationErrorSuiteValidator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/suite-validator.ts"""
    field: Any = None
    message: Any = None
    value: Any = None

@dataclass
class ValidationResultSuiteValidator:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/suite-validator.ts"""
    valid: Any = None
    errors: Any = None
    warnings: Any = None
    missingTests: Any = None
    suite: Any = None

@dataclass
class ExecutionConfigTestExecutor:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/test-executor.ts"""
    defaultTimeout: Any = None
    projectPath: Any = None
    defaultModel: Any = None
    debug: Any = None

@dataclass
class ExecutionLoggerTestExecutor:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/test-executor.ts"""
    data: Any = None

@dataclass
class ExecutionResultTestExecutor:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/test-executor.ts"""
    sessionId: Any = None
    events: Any = None
    errors: Any = None
    approvalsGiven: Any = None
    duration: Any = None

@dataclass
class TestResultTestRunner:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/test-runner.ts"""
    testCase: Any = None
    sessionId: Any = None
    passed: Any = None
    errors: Any = None
    events: Any = None
    duration: Any = None
    approvalsGiven: Any = None
    sessionPath: Any = None
    evaluation: Any = None

@dataclass
class TestRunnerConfigTestRunner:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/test-runner.ts"""
    port: Any = None
    debug: Any = None
    defaultTimeout: Any = None
    projectPath: Any = None
    runEvaluators: Any = None
    defaultModel: Any = None

@dataclass
class ValidationStatsValidateSuitesCli:
    """Source: vendor/OpenAgentsControl/evals/framework/src/sdk/validate-suites-cli.ts"""
    totalSuites: Any = None
    validSuites: Any = None
    invalidSuites: Any = None
    totalErrors: Any = None
    totalWarnings: Any = None

@dataclass
class ApprovalGateCheckIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    approvalRequested: Any = None
    approvalTimestamp: Any = None
    executionTimestamp: Any = None
    timeDiffMs: Any = None
    toolName: Any = None
    approvalConfidence: Any = None
    approvalText: Any = None
    whatIsBeingApproved: Any = None
    evidence: Any = None

@dataclass
class CheckIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    name: Any = None
    passed: Any = None
    weight: Any = None
    evidence: Any = None

@dataclass
class ContextLoadingCheckIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    contextFileLoaded: Any = None
    contextFilePath: Any = None
    loadTimestamp: Any = None
    executionTimestamp: Any = None
    requiredContext: Any = None
    taskType: Any = None
    expectedContextFiles: Any = None
    actualContextFiles: Any = None
    evidence: Any = None

@dataclass
class DelegationCheckIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    shouldDelegate: Any = None
    didDelegate: Any = None
    fileCount: Any = None
    delegationThreshold: Any = None
    evidence: Any = None

@dataclass
class EvaluationResultIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    evaluator: Any = None
    passed: Any = None
    score: Any = None
    violations: Any = None
    evidence: Any = None
    metadata: Any = None

@dataclass
class EvaluatorConfigIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    enabled: Any = None
    weight: Any = None
    options: Any = None

@dataclass
class EvaluatorRegistryIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    data: Any = None

@dataclass
class EvidenceIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    type: Any = None
    description: Any = None
    data: Any = None
    timestamp: Any = None

@dataclass
class ExpectedBehaviorIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    no_execution_tools: Any = None
    no_approval_required: Any = None
    approval_requested: Any = None
    context_loaded: Any = None
    context_file: Any = None
    delegation_used: Any = None
    tool_used: Any = None
    min_file_count: Any = None
    response_provided: Any = None

@dataclass
class FrameworkConfigIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    projectPath: Any = None
    sessionStoragePath: Any = None
    resultsPath: Any = None
    passThreshold: Any = None

@dataclass
class IEvaluatorIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    name: Any = None
    description: Any = None

@dataclass
class MessageIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    id: Any = None
    role: Any = None
    sessionID: Any = None
    mode: Any = None
    modelID: Any = None
    providerID: Any = None
    tokens: Any = None
    cost: Any = None
    time: Any = None
    completed: Any = None

@dataclass
class MessageMetricsIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    tokens: Any = None
    cost: Any = None
    duration: Any = None

@dataclass
class MessageWithPartsIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    info: Any = None
    parts: Any = None

@dataclass
class ModelInfoIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    modelID: Any = None
    providerID: Any = None

@dataclass
class PartIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    id: Any = None
    messageID: Any = None
    sessionID: Any = None
    type: Any = None
    time: Any = None
    completed: Any = None

@dataclass
class SessionInfoIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    id: Any = None
    version: Any = None
    title: Any = None
    time: Any = None
    updated: Any = None

@dataclass
class TaskContextIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    type: Any = None
    userMessage: Any = None
    requiredContext: Any = None

@dataclass
class TestCaseIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    id: Any = None
    name: Any = None
    description: Any = None
    category: Any = None
    input: Any = None
    expected_behavior: Any = None
    evaluators: Any = None
    pass_threshold: Any = None

@dataclass
class TestResultIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    testCaseId: Any = None
    sessionId: Any = None
    passed: Any = None
    score: Any = None
    evaluationResults: Any = None
    violations: Any = None
    evidence: Any = None
    metadata: Any = None
    duration: Any = None
    agent: Any = None
    model: Any = None
    cost: Any = None

@dataclass
class TestSuiteIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    name: Any = None
    timestamp: Any = None
    testResults: Any = None
    summary: Any = None
    passed: Any = None
    failed: Any = None
    passRate: Any = None
    avgScore: Any = None

@dataclass
class TimelineEventIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    timestamp: Any = None
    type: Any = None
    agent: Any = None
    model: Any = None
    messageId: Any = None
    partId: Any = None
    data: Any = None

@dataclass
class TokenUsageIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    input: Any = None
    output: Any = None
    total: Any = None

@dataclass
class ToolUsageCheckIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    correctToolUsed: Any = None
    toolUsed: Any = None
    expectedTool: Any = None
    reason: Any = None
    evidence: Any = None

@dataclass
class ViolationIndex:
    """Source: vendor/OpenAgentsControl/evals/framework/src/types/index.ts"""
    type: Any = None
    severity: Any = None
    message: Any = None
    timestamp: Any = None
    evidence: Any = None

@dataclass
class AbilityListItemIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/loader/index.ts"""
    data: Any = None

@dataclass
class ChatMessageOutputPlugin:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts"""
    parts: Any = None

@dataclass
class EventInputPlugin:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts"""
    data: Any = None

@dataclass
class OpencodeClientPlugin:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts"""
    session: Any = None

@dataclass
class PluginConfigPlugin:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts"""
    data: Any = None

@dataclass
class PluginContextPlugin:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts"""
    data: Any = None

@dataclass
class SessionIdleOutputPlugin:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts"""
    data: Any = None

@dataclass
class ToolExecuteInputPlugin:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts"""
    data: Any = None

@dataclass
class ToolExecuteOutputPlugin:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/plugin.ts"""
    data: Any = None

@dataclass
class AbilitiesSDKOptionsSdk:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/sdk.ts"""
    data: Any = None

@dataclass
class AbilityInfoSdk:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/sdk.ts"""
    data: Any = None

@dataclass
class ExecutionResultSdk:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/sdk.ts"""
    data: Any = None

@dataclass
class AbilityIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class AbilityExecutionIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class ExecutorContextIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class InputDefinitionIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class LoadedAbilityIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class LoaderOptionsIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class ScriptStepIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class StepResultIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class ValidationErrorIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None

@dataclass
class ValidationResultIndex:
    """Source: vendor/OpenAgentsControl/packages/plugin-abilities/src/types/index.ts"""
    data: Any = None
