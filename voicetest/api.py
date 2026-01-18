"""Core API for voicetest.

This is the single interface for all consumers. CLI and Web UI are thin wrappers.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from voicetest.importers.base import ImporterInfo
from voicetest.importers.registry import get_registry
from voicetest.models.agent import AgentGraph
from voicetest.models.results import (
    Message,
    MetricResult,
    ModelOverride,
    ModelsUsed,
    TestResult,
    TestRun,
)
from voicetest.models.test_case import RunOptions, TestCase

# Callback type for turn updates
OnTurnCallback = Callable[[list[Message]], Awaitable[None] | None]


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
    registry = get_registry()
    return registry.import_agent(config, source_type=source)


def list_importers() -> list[ImporterInfo]:
    """List available importers with their capabilities.

    Returns:
        List of ImporterInfo objects describing each available importer.
    """
    registry = get_registry()
    return registry.list_importers()


async def export_agent(
    graph: AgentGraph,
    format: str,
    output: Path | None = None,
) -> str:
    """Export agent graph to specified format.

    Args:
        graph: The agent graph to export.
        format: Export format ('livekit', 'mermaid', 'retell-llm', 'retell-cf').
        output: Optional output path. Returns string if None.

    Returns:
        Exported content as string.
    """
    import json

    if format == "mermaid":
        from voicetest.exporters.graph_viz import export_mermaid

        content = export_mermaid(graph)
    elif format == "livekit":
        from voicetest.exporters.livekit_codegen import export_livekit_code

        content = export_livekit_code(graph)
    elif format == "retell-llm":
        from voicetest.exporters.retell_llm import export_retell_llm

        content = json.dumps(export_retell_llm(graph), indent=2)
    elif format == "retell-cf":
        from voicetest.exporters.retell_cf import export_retell_cf

        content = json.dumps(export_retell_cf(graph), indent=2)
    else:
        raise ValueError(f"Unknown export format: {format}")

    if output:
        output.write_text(content)

    return content


def list_export_formats() -> list[dict[str, str]]:
    """List available export formats.

    Returns:
        List of dicts with format id and description.
    """
    return [
        {"id": "mermaid", "name": "Mermaid", "description": "Mermaid flowchart diagram"},
        {"id": "livekit", "name": "LiveKit", "description": "LiveKit Python agent code"},
        {"id": "retell-llm", "name": "Retell LLM", "description": "Retell LLM JSON format"},
        {"id": "retell-cf", "name": "Retell CF", "description": "Retell Conversation Flow JSON"},
    ]


async def run_test(
    graph: AgentGraph,
    test_case: TestCase,
    options: RunOptions | None = None,
    _mock_mode: bool = False,
    on_turn: OnTurnCallback | None = None,
) -> TestResult:
    """Run a single test case against an agent.

    Args:
        graph: The agent graph to test.
        test_case: Test case definition.
        options: Optional run options.
        _mock_mode: If True, use mock responses (for testing).
        on_turn: Optional callback invoked after each turn with current transcript.

    Returns:
        TestResult with pass/fail status, transcript, and metrics.
    """
    from voicetest.engine.session import ConversationRunner
    from voicetest.judges.flow import FlowJudge
    from voicetest.judges.metric import MetricJudge
    from voicetest.judges.rule import RuleJudge
    from voicetest.simulator.user_sim import SimulatorResponse, UserSimulator

    options = options or RunOptions()
    default_options = RunOptions()
    overrides: list[ModelOverride] = []

    # Use test case's llm_model as fallback for agent_model
    if test_case.llm_model and options.agent_model == default_options.agent_model:
        options = options.model_copy(update={"agent_model": test_case.llm_model})
        overrides.append(
            ModelOverride(
                role="agent",
                requested=default_options.agent_model,
                actual=test_case.llm_model,
                reason="test_case.llm_model used (settings were default)",
            )
        )
    elif test_case.llm_model and options.agent_model != test_case.llm_model:
        # Settings override test's requested model
        overrides.append(
            ModelOverride(
                role="agent",
                requested=test_case.llm_model,
                actual=options.agent_model,
                reason="settings override test_case.llm_model",
            )
        )

    models_used = ModelsUsed(
        agent=options.agent_model,
        simulator=options.simulator_model,
        judge=options.judge_model,
    )

    start_time = datetime.now()

    try:
        # Setup components
        runner = ConversationRunner(graph, options, mock_mode=_mock_mode)
        simulator = UserSimulator(test_case.user_prompt, options.simulator_model)
        metric_judge = MetricJudge(options.judge_model)
        rule_judge = RuleJudge()
        flow_judge = FlowJudge(options.judge_model)

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
            metric_judge._mock_results = [
                MetricResult(metric=m, passed=True, reasoning="Mock evaluation", confidence=0.9)
                for m in test_case.metrics
            ]
            flow_judge._mock_mode = True
            from voicetest.judges.flow import FlowResult

            flow_judge._mock_result = FlowResult(
                valid=True, issues=[], reasoning="Mock flow validation"
            )

        # Run conversation
        state = await runner.run(test_case, simulator, on_turn=on_turn)

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
            metric_results = await metric_judge.evaluate_all(state.transcript, test_case.metrics)

        # Check flow constraints (optional, informational only)
        flow_issues: list[str] = []
        if options.flow_judge:
            flow_result = await flow_judge.evaluate(
                graph.nodes, state.transcript, state.nodes_visited
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

    except Exception as e:
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        return TestResult(
            test_id=test_case.name,
            test_name=test_case.name,
            status="error",
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
    from voicetest.judges.metric import MetricJudge

    judge = MetricJudge()

    if _mock_mode:
        judge._mock_mode = True
        judge._mock_results = [
            MetricResult(metric=m, passed=True, reasoning="Mock evaluation", confidence=0.9)
            for m in metrics
        ]

    return await judge.evaluate_all(transcript, metrics)
