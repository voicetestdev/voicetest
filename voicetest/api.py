"""Core API for voicetest.

This is the single interface for all consumers. CLI and Web UI are thin wrappers.
"""

from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
import logging
from pathlib import Path
import uuid

from voicetest.audio import AudioRoundTrip
from voicetest.container import get_exporter_registry
from voicetest.container import get_importer_registry
from voicetest.engine.session import ConversationRunner
from voicetest.importers.base import ImporterInfo
from voicetest.judges.diagnosis import DiagnosisJudge
from voicetest.judges.flow import FlowJudge
from voicetest.judges.flow import FlowResult
from voicetest.judges.metric import MetricJudge
from voicetest.judges.rule import RuleJudge
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import MetricsConfig
from voicetest.models.diagnosis import Diagnosis
from voicetest.models.diagnosis import DiagnosisResult
from voicetest.models.diagnosis import FixAttemptResult
from voicetest.models.diagnosis import FixSuggestion
from voicetest.models.diagnosis import PromptChange
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.results import ModelOverride
from voicetest.models.results import ModelsUsed
from voicetest.models.results import TestResult
from voicetest.models.results import TestRun
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.retry import OnErrorCallback
from voicetest.settings import Settings
from voicetest.settings import resolve_model
from voicetest.simulator.user_sim import SimulatorResponse
from voicetest.simulator.user_sim import UserSimulator
from voicetest.templating import substitute_variables


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


async def evaluate_global_metrics(
    transcript: list[Message],
    metrics_config: MetricsConfig,
    judge_model: str,
    on_error: OnErrorCallback | None = None,
    use_heard: bool = False,
) -> list[MetricResult]:
    """Evaluate a transcript against an agent's global metrics.

    Args:
        transcript: Conversation transcript to evaluate.
        metrics_config: Agent metrics configuration with threshold and global metrics.
        judge_model: LLM model to use for evaluation.
        on_error: Optional callback for retry notifications.
        use_heard: If True, use metadata["heard"] for assistant messages.

    Returns:
        List of MetricResult objects for each enabled global metric.
    """
    metric_judge = MetricJudge(judge_model)
    threshold = metrics_config.threshold
    results: list[MetricResult] = []

    for gm in metrics_config.global_metrics:
        if gm.enabled:
            gm_threshold = gm.threshold if gm.threshold is not None else threshold
            result = await metric_judge.evaluate(
                transcript,
                gm.criteria,
                threshold=gm_threshold,
                on_error=on_error,
                use_heard=use_heard,
            )
            result = result.model_copy(update={"metric": f"[{gm.name}]"})
            results.append(result)

    return results


def _model_overrides(
    role: str,
    settings_value: str | None,
    role_default: str | None,
    resolved: str,
    test_model_precedence: bool,
) -> list[ModelOverride]:
    """Generate diagnostic override records when resolved model differs from inputs."""
    if not role_default or not settings_value:
        if role_default and not settings_value:
            return [
                ModelOverride(
                    role=role,
                    requested="(not configured)",
                    actual=role_default,
                    reason=f"role default used (global {role} not configured)",
                )
            ]
        return []
    if role_default == settings_value:
        return []
    if resolved == role_default:
        return [
            ModelOverride(
                role=role,
                requested=settings_value,
                actual=role_default,
                reason="role default used (test_model_precedence enabled)",
            )
        ]
    return [
        ModelOverride(
            role=role,
            requested=role_default,
            actual=settings_value,
            reason=f"global settings override {role} default",
        )
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
    tmp = options.test_model_precedence

    # Resolve models via central precedence chain
    resolved_agent = resolve_model(options.agent_model, graph.default_model, tmp)
    resolved_sim = resolve_model(options.simulator_model, test_case.llm_model, tmp)
    resolved_judge = resolve_model(options.judge_model)

    # Track overrides for diagnostics
    overrides.extend(
        _model_overrides("agent", options.agent_model, graph.default_model, resolved_agent, tmp)
    )
    overrides.extend(
        _model_overrides(
            "simulator", options.simulator_model, test_case.llm_model, resolved_sim, tmp
        )
    )

    options = options.model_copy(
        update={
            "agent_model": resolved_agent,
            "simulator_model": resolved_sim,
            "judge_model": resolved_judge,
        }
    )

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
            use_split_transitions=options.split_transitions,
        )
        simulator = UserSimulator(user_prompt, options.simulator_model)
        metric_judge = MetricJudge(options.judge_model)
        rule_judge = RuleJudge(pattern_engine=options.pattern_engine)
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
            global_results = await evaluate_global_metrics(
                state.transcript,
                metrics_config,
                judge_model=options.judge_model,
                on_error=on_error,
            )
            metric_results.extend(global_results)

        # Audio evaluation (when enabled)
        audio_metric_results: list[MetricResult] = []
        if options.audio_eval:
            try:
                audio_rt = AudioRoundTrip.from_settings()
                state.transcript = await audio_rt.transform_transcript(state.transcript)

                if test_type == "rule":
                    audio_metric_results = await rule_judge.evaluate(
                        state.transcript,
                        test_case.includes,
                        test_case.excludes,
                        test_case.patterns,
                        use_heard=True,
                    )
                else:
                    audio_metric_results = await metric_judge.evaluate_all(
                        state.transcript,
                        test_case.metrics,
                        threshold=threshold,
                        on_error=on_error,
                        use_heard=True,
                    )

                if metrics_config:
                    audio_global_results = await evaluate_global_metrics(
                        state.transcript,
                        metrics_config,
                        judge_model=options.judge_model,
                        on_error=on_error,
                        use_heard=True,
                    )
                    audio_metric_results.extend(audio_global_results)

                await audio_rt.close()
            except Exception:
                logging.getLogger(__name__).exception("Audio evaluation failed")

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
            audio_metric_results=audio_metric_results,
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


async def audio_eval_result(
    transcript: list[Message],
    test_case: TestCase,
    metrics_config: MetricsConfig | None = None,
    judge_model: str | None = None,
    settings: Settings | None = None,
) -> tuple[list[Message], list[MetricResult]]:
    """Run audio evaluation on an existing transcript.

    Performs TTS→STT round-trip on assistant messages and re-evaluates
    metrics using the "heard" text.

    Args:
        transcript: Conversation transcript to evaluate.
        test_case: Test case with metrics/rules to evaluate against.
        metrics_config: Optional agent metrics config for global metrics.
        judge_model: LLM model for evaluation.
        settings: Settings for audio service URLs.

    Returns:
        Tuple of (transformed transcript, audio metric results).
    """
    if settings is None:
        settings = Settings()

    audio_rt = AudioRoundTrip.from_settings(settings)
    transformed = await audio_rt.transform_transcript(transcript)

    judge_model = judge_model or resolve_model()
    test_type = test_case.effective_type

    threshold = metrics_config.threshold if metrics_config else 0.7

    if test_type == "rule":
        rule_judge = RuleJudge(pattern_engine=settings.run.pattern_engine)
        audio_metrics = await rule_judge.evaluate(
            transformed,
            test_case.includes,
            test_case.excludes,
            test_case.patterns,
            use_heard=True,
        )
    else:
        metric_judge = MetricJudge(judge_model)
        audio_metrics = await metric_judge.evaluate_all(
            transformed,
            test_case.metrics,
            threshold=threshold,
            use_heard=True,
        )

    if metrics_config:
        global_results = await evaluate_global_metrics(
            transformed,
            metrics_config,
            judge_model=judge_model,
            use_heard=True,
        )
        audio_metrics.extend(global_results)

    await audio_rt.close()
    return transformed, audio_metrics


async def evaluate_transcript(
    transcript: list[Message],
    metrics: list[str],
    judge_model: str | None = None,
    _mock_mode: bool = False,
) -> list[MetricResult]:
    """Evaluate an existing transcript against metrics (no simulation).

    Args:
        transcript: Conversation transcript to evaluate.
        metrics: List of metric criteria strings.
        judge_model: LLM model for evaluation. Uses resolve_model() if None.
        _mock_mode: If True, use mock responses (for testing).

    Returns:
        List of MetricResult objects.
    """
    judge = MetricJudge(judge_model or resolve_model())

    if _mock_mode:
        judge._mock_mode = True
        judge._mock_results = [
            MetricResult(metric=m, passed=True, reasoning="Mock evaluation", confidence=0.9)
            for m in metrics
        ]

    return await judge.evaluate_all(transcript, metrics)


def apply_fix_to_graph(graph: AgentGraph, changes: list[PromptChange]) -> AgentGraph:
    """Apply proposed text changes to a deep copy of the agent graph.

    Handles three location types:
    - general_prompt: replaces source_metadata["general_prompt"]
    - node_prompt: replaces node.state_prompt
    - transition: replaces transition.condition.value

    Skips changes that reference nonexistent nodes or transitions.
    Does NOT persist anything.

    Args:
        graph: The original agent graph (not modified).
        changes: List of text changes to apply.

    Returns:
        A deep copy of the graph with changes applied.
    """
    modified = graph.model_copy(deep=True)

    for change in changes:
        if change.location_type == "general_prompt":
            if "general_prompt" in modified.source_metadata:
                modified.source_metadata["general_prompt"] = change.proposed_text

        elif change.location_type == "node_prompt":
            node = modified.nodes.get(change.node_id) if change.node_id else None
            if node:
                node.state_prompt = change.proposed_text

        elif change.location_type == "transition":
            node = modified.nodes.get(change.node_id) if change.node_id else None
            if node and change.transition_target_id:
                for t in node.transitions:
                    if t.target_node_id == change.transition_target_id:
                        t.condition.value = change.proposed_text
                        break

    return modified


def scores_improved(original: dict[str, float], new: dict[str, float]) -> bool:
    """Check if average scores improved.

    Args:
        original: Original metric scores by name.
        new: Post-fix metric scores by name.

    Returns:
        True if the average of new scores is strictly greater than original.
    """
    if not original or not new:
        return False

    orig_avg = sum(original.values()) / len(original)
    new_avg = sum(new.values()) / len(new)
    return new_avg > orig_avg


async def diagnose_failure(
    graph: AgentGraph,
    transcript: list[Message],
    nodes_visited: list[str],
    failed_metrics: list[MetricResult],
    test_scenario: str,
    judge_model: str,
) -> DiagnosisResult:
    """Diagnose a test failure and suggest a fix.

    Args:
        graph: The agent graph that was tested.
        transcript: Conversation transcript from the failed test.
        nodes_visited: Sequence of node IDs visited during the test.
        failed_metrics: Metric results (including failures).
        test_scenario: The user prompt / test scenario.
        judge_model: LLM model for diagnosis.

    Returns:
        DiagnosisResult with diagnosis and suggested fix.
    """
    judge = DiagnosisJudge(judge_model)
    diagnosis = await judge.diagnose(
        graph, transcript, nodes_visited, failed_metrics, test_scenario
    )
    fix = await judge.suggest_fix(graph, diagnosis, failed_metrics)
    return DiagnosisResult(diagnosis=diagnosis, fix=fix)


async def apply_and_rerun(
    graph: AgentGraph,
    test_case: TestCase,
    changes: list[PromptChange],
    original_metrics: list[MetricResult],
    iteration: int,
    options: RunOptions | None = None,
    metrics_config: MetricsConfig | None = None,
) -> FixAttemptResult:
    """Apply changes to graph, rerun test, and compare results.

    Args:
        graph: The original agent graph.
        test_case: Test case to rerun.
        changes: Proposed text changes.
        original_metrics: Metrics from the original (failed) run.
        iteration: Iteration number.
        options: Run options.
        metrics_config: Metrics configuration.

    Returns:
        FixAttemptResult with comparison data.
    """
    modified_graph = apply_fix_to_graph(graph, changes)
    result = await run_test(modified_graph, test_case, options, metrics_config)

    original_scores = {
        m.metric: (m.score if m.score is not None else (1.0 if m.passed else 0.0))
        for m in original_metrics
    }
    new_scores = {
        m.metric: (m.score if m.score is not None else (1.0 if m.passed else 0.0))
        for m in result.metric_results
    }

    return FixAttemptResult(
        iteration=iteration,
        changes_applied=changes,
        test_passed=result.status == "pass",
        metric_results=[m.model_dump() for m in result.metric_results],
        improved=scores_improved(original_scores, new_scores),
        original_scores=original_scores,
        new_scores=new_scores,
    )


async def revise_fix(
    graph: AgentGraph,
    diagnosis: Diagnosis,
    prev_changes: list[PromptChange],
    new_metrics: list[MetricResult],
    judge_model: str,
) -> FixSuggestion:
    """Revise a previous fix suggestion based on new metric results.

    Args:
        graph: The agent graph (after previous fix was applied).
        diagnosis: Original diagnosis.
        prev_changes: Changes that were applied in the previous attempt.
        new_metrics: Metric results after previous fix.
        judge_model: LLM model for revision.

    Returns:
        Revised FixSuggestion.
    """
    judge = DiagnosisJudge(judge_model)
    return await judge.revise_fix(graph, diagnosis, prev_changes, new_metrics)
