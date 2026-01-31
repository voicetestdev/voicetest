"""Core API for voicetest.

This is the single interface for all consumers. CLI and Web UI are thin wrappers.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
import uuid

from voicetest.container import get_exporter_registry, get_importer_registry
from voicetest.engine.session import ConversationRunner
from voicetest.importers.base import ImporterInfo
from voicetest.judges.flow import FlowJudge, FlowResult
from voicetest.judges.metric import MetricJudge
from voicetest.judges.rule import RuleJudge
from voicetest.models.agent import AgentGraph, MetricsConfig
from voicetest.models.results import (
    Message,
    MetricResult,
    ModelOverride,
    ModelsUsed,
    TestResult,
    TestRun,
)
from voicetest.models.test_case import RunOptions, TestCase
from voicetest.retry import OnErrorCallback
from voicetest.settings import DEFAULT_MODEL
from voicetest.simulator.user_sim import SimulatorResponse, UserSimulator
from voicetest.utils import substitute_variables


# Callback type for turn updates
OnTurnCallback = Callable[[list[Message]], Awaitable[None] | None]

# Callback type for token updates: receives token string and source ("agent" or "user")
OnTokenCallback = Callable[[str, str], Awaitable[None] | None]


async def import_agent(
    config: str | Path | dict | Callable,
    source: str | None = None,
) -> AgentGraph:
    """Import agent config from any supported source.

    Args:
        config: Path to config file, config dict, or callable returning AgentGraph.
        source: Source type (e.g., 'retell', 'custom'). Auto-detected if None.

    Returns:
        AgentGraph representing the agent workflow.

    Raises:
        ValueError: If source type is unknown or cannot be auto-detected.
    """
    registry = get_importer_registry()
    return registry.import_agent(config, source_type=source)


def list_importers() -> list[ImporterInfo]:
    """List available importers with their capabilities.

    Returns:
        List of ImporterInfo objects describing each available importer.
    """
    registry = get_importer_registry()
    return registry.list_importers()


async def export_agent(
    graph: AgentGraph,
    format: str,
    output: Path | None = None,
) -> str:
    """Export agent graph to specified format.

    Args:
        graph: The agent graph to export.
        format: Export format (see list_export_formats()).
        output: Optional output path. Returns string if None.

    Returns:
        Exported content as string.
    """
    registry = get_exporter_registry()
    content = registry.export(graph, format)

    if output:
        output.write_text(content)

    return content


def list_export_formats() -> list[dict[str, str]]:
    """List available export formats.

    Returns:
        List of dicts with format id, name, description, and extension.
    """
    registry = get_exporter_registry()
    return [
        {"id": info.format_id, "name": info.name, "description": info.description, "ext": info.ext}
        for info in registry.list_formats()
    ]


async def run_test(
    graph: AgentGraph,
    test_case: TestCase,
    options: RunOptions | None = None,
    metrics_config: MetricsConfig | None = None,
    _mock_mode: bool = False,
    on_turn: OnTurnCallback | None = None,
    on_token: OnTokenCallback | None = None,
    on_error: OnErrorCallback | None = None,
) -> TestResult:
    """Run a single test case against an agent.

    Args:
        graph: The agent graph to test.
        test_case: Test case definition.
        options: Optional run options.
        metrics_config: Optional metrics configuration with threshold and global metrics.
        _mock_mode: If True, use mock responses (for testing).
        on_turn: Optional callback invoked after each turn with current transcript.
        on_token: Optional callback invoked for each token during streaming.
        on_error: Optional callback invoked on retryable errors (e.g., rate limits).

    Returns:
        TestResult with pass/fail status, transcript, and metrics.
    """
    options = options or RunOptions()
    overrides: list[ModelOverride] = []

    # Resolve agent_model with graph.default_model precedence
    # Precedence: global (if set) > agent.default_model > DEFAULT_MODEL
    if graph.default_model:
        if options.agent_model is None:
            # Global not configured, agent's default wins
            options = options.model_copy(update={"agent_model": graph.default_model})
            overrides.append(
                ModelOverride(
                    role="agent",
                    requested="(not configured)",
                    actual=graph.default_model,
                    reason="agent.default_model used (global agent not configured)",
                )
            )
        elif options.test_model_precedence:
            # Toggle enabled, agent's default wins over explicit global
            if options.agent_model != graph.default_model:
                overrides.append(
                    ModelOverride(
                        role="agent",
                        requested=options.agent_model,
                        actual=graph.default_model,
                        reason="agent.default_model used (test_model_precedence enabled)",
                    )
                )
                options = options.model_copy(update={"agent_model": graph.default_model})
        else:
            # Global explicitly set, global wins
            if options.agent_model != graph.default_model:
                overrides.append(
                    ModelOverride(
                        role="agent",
                        requested=graph.default_model,
                        actual=options.agent_model,
                        reason="global settings override agent.default_model",
                    )
                )
    elif options.agent_model is None:
        # No agent default, no global, use DEFAULT_MODEL
        options = options.model_copy(update={"agent_model": DEFAULT_MODEL})

    # Resolve simulator_model with test_case.llm_model precedence
    # test_case.llm_model controls the simulator (simulated user), not the agent
    if test_case.llm_model:
        if options.simulator_model is None:
            # Global not configured, test wins
            options = options.model_copy(update={"simulator_model": test_case.llm_model})
            overrides.append(
                ModelOverride(
                    role="simulator",
                    requested="(not configured)",
                    actual=test_case.llm_model,
                    reason="test_case.llm_model used (global simulator not configured)",
                )
            )
        elif options.test_model_precedence:
            # Toggle enabled, test wins over explicit global
            if options.simulator_model != test_case.llm_model:
                overrides.append(
                    ModelOverride(
                        role="simulator",
                        requested=options.simulator_model,
                        actual=test_case.llm_model,
                        reason="test_case.llm_model used (test_model_precedence enabled)",
                    )
                )
                options = options.model_copy(update={"simulator_model": test_case.llm_model})
        else:
            # Global explicitly set, global wins
            if options.simulator_model != test_case.llm_model:
                overrides.append(
                    ModelOverride(
                        role="simulator",
                        requested=test_case.llm_model,
                        actual=options.simulator_model,
                        reason="global settings override test_case.llm_model",
                    )
                )
    elif options.simulator_model is None:
        # No test model, no global, use default
        options = options.model_copy(update={"simulator_model": DEFAULT_MODEL})

    # Resolve judge_model (no test override, just global or default)
    if options.judge_model is None:
        options = options.model_copy(update={"judge_model": DEFAULT_MODEL})

    models_used = ModelsUsed(
        agent=options.agent_model,
        simulator=options.simulator_model,
        judge=options.judge_model,
    )

    start_time = datetime.now()

    # Track transcript for error recovery
    error_transcript: list[Message] = []

    # Wrap on_turn to capture transcript
    original_on_turn = on_turn

    async def tracking_on_turn(transcript: list[Message]) -> None:
        error_transcript.clear()
        error_transcript.extend(transcript)
        if original_on_turn:
            result = original_on_turn(transcript)
            if result is not None and hasattr(result, "__await__"):
                await result

    try:
        # Substitute dynamic variables
        dynamic_vars = test_case.dynamic_variables
        user_prompt = substitute_variables(test_case.user_prompt, dynamic_vars)

        # Setup components
        runner = ConversationRunner(
            graph,
            options,
            mock_mode=_mock_mode,
            dynamic_variables=dynamic_vars,
            use_cot_transitions=options.cot_transitions,
        )
        simulator = UserSimulator(user_prompt, options.simulator_model)
        metric_judge = MetricJudge(options.judge_model)
        rule_judge = RuleJudge()
        flow_judge = FlowJudge(options.judge_model)

        # Get threshold from metrics_config or use default
        threshold = metrics_config.threshold if metrics_config else 0.7

        # Enable mock mode for testing
        if _mock_mode:
            simulator._mock_mode = True
            simulator._mock_responses = [
                SimulatorResponse(
                    message="Hello, I need help.",
                    should_end=False,
                    reasoning="Starting conversation",
                ),
                SimulatorResponse(
                    message="Thanks, that's helpful.",
                    should_end=False,
                    reasoning="Responding to agent",
                ),
                SimulatorResponse(message="", should_end=True, reasoning="Goal achieved"),
            ]
            metric_judge._mock_mode = True

            # Build mock results for test metrics + enabled global metrics
            mock_results = [
                MetricResult(
                    metric=m,
                    score=0.9,
                    passed=True,
                    reasoning="Mock evaluation",
                    threshold=threshold,
                    confidence=0.9,
                )
                for m in test_case.metrics
            ]
            if metrics_config:
                for gm in metrics_config.global_metrics:
                    if gm.enabled:
                        gm_threshold = gm.threshold if gm.threshold is not None else threshold
                        mock_results.append(
                            MetricResult(
                                metric=f"[{gm.name}]",
                                score=0.9,
                                passed=True,
                                reasoning="Mock global metric evaluation",
                                threshold=gm_threshold,
                                confidence=0.9,
                            )
                        )
            metric_judge._mock_results = mock_results

            flow_judge._mock_mode = True
            flow_judge._mock_result = FlowResult(
                valid=True, issues=[], reasoning="Mock flow validation"
            )

        # Run conversation
        state = await runner.run(
            test_case, simulator, on_turn=tracking_on_turn, on_token=on_token, on_error=on_error
        )

        # Evaluate based on test type
        test_type = test_case.effective_type
        if test_type == "rule":
            # Rule-based evaluation (deterministic pattern matching)
            metric_results = await rule_judge.evaluate(
                state.transcript,
                test_case.includes,
                test_case.excludes,
                test_case.patterns,
            )
        else:
            # LLM-based evaluation (semantic metrics)
            metric_results = await metric_judge.evaluate_all(
                state.transcript, test_case.metrics, threshold=threshold, on_error=on_error
            )

        # Evaluate global metrics if configured
        if metrics_config:
            for gm in metrics_config.global_metrics:
                if gm.enabled:
                    gm_threshold = gm.threshold if gm.threshold is not None else threshold
                    result = await metric_judge.evaluate(
                        state.transcript,
                        gm.criteria,
                        threshold=gm_threshold,
                        on_error=on_error,
                    )
                    # Override metric name to show global metric info
                    result = result.model_copy(update={"metric": f"[{gm.name}]"})
                    metric_results.append(result)

        # Check flow constraints (optional, informational only)
        flow_issues: list[str] = []
        if options.flow_judge:
            flow_result = await flow_judge.evaluate(
                graph.nodes, state.transcript, state.nodes_visited, on_error=on_error
            )
            flow_issues = flow_result.issues

        # Determine overall status (based on metrics only)
        metrics_passed = all(r.passed for r in metric_results)
        status = "pass" if metrics_passed else "fail"

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return TestResult(
            test_id=test_case.name,
            test_name=test_case.name,
            status=status,
            transcript=state.transcript,
            metric_results=metric_results,
            nodes_visited=state.nodes_visited,
            tools_called=state.tools_called,
            constraint_violations=flow_issues,
            turn_count=state.turn_count,
            duration_ms=duration_ms,
            end_reason=state.end_reason,
            models_used=models_used,
            model_overrides=overrides,
        )

    except BaseExceptionGroup as eg:
        # DSPy streamify wraps exceptions in ExceptionGroup - unwrap to surface real error
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        real_error = eg.exceptions[0] if eg.exceptions else eg
        return TestResult(
            test_id=test_case.name,
            test_name=test_case.name,
            status="error",
            transcript=error_transcript,
            duration_ms=duration_ms,
            error_message=str(real_error),
            models_used=models_used,
            model_overrides=overrides,
        )
    except Exception as e:
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        return TestResult(
            test_id=test_case.name,
            test_name=test_case.name,
            status="error",
            transcript=error_transcript,
            duration_ms=duration_ms,
            error_message=str(e),
            models_used=models_used,
            model_overrides=overrides,
        )


async def run_tests(
    graph: AgentGraph,
    test_cases: list[TestCase],
    options: RunOptions | None = None,
    _mock_mode: bool = False,
) -> TestRun:
    """Run multiple test cases, return aggregated results.

    Args:
        graph: The agent graph to test.
        test_cases: List of test case definitions.
        options: Optional run options.
        _mock_mode: If True, use mock responses (for testing).

    Returns:
        TestRun with aggregated results.
    """
    run_id = str(uuid.uuid4())
    started_at = datetime.now()

    results = []
    for test_case in test_cases:
        result = await run_test(graph, test_case, options, _mock_mode=_mock_mode)
        results.append(result)

    return TestRun(
        run_id=run_id,
        started_at=started_at,
        completed_at=datetime.now(),
        results=results,
    )


async def evaluate_transcript(
    transcript: list[Message],
    metrics: list[str],
    _mock_mode: bool = False,
) -> list[MetricResult]:
    """Evaluate an existing transcript against metrics (no simulation).

    Args:
        transcript: Conversation transcript to evaluate.
        metrics: List of metric criteria strings.
        _mock_mode: If True, use mock responses (for testing).

    Returns:
        List of MetricResult objects.
    """
    judge = MetricJudge()

    if _mock_mode:
        judge._mock_mode = True
        judge._mock_results = [
            MetricResult(metric=m, passed=True, reasoning="Mock evaluation", confidence=0.9)
            for m in metrics
        ]

    return await judge.evaluate_all(transcript, metrics)
