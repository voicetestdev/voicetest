"""Diagnosis service: diagnose failures and suggest/apply fixes."""

from voicetest.judges.diagnosis import DiagnosisJudge
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import MetricsConfig
from voicetest.models.diagnosis import Diagnosis
from voicetest.models.diagnosis import DiagnosisResult
from voicetest.models.diagnosis import FixAttemptResult
from voicetest.models.diagnosis import FixSuggestion
from voicetest.models.diagnosis import PromptChange
from voicetest.models.results import MetricResult
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.services.testing.execution import TestExecutionService


class DiagnosisService:
    """Diagnoses test failures and suggests prompt fixes. Stateless."""

    def __init__(self, test_execution_service: TestExecutionService):
        self._execution = test_execution_service

    async def diagnose_failure(
        self,
        graph: AgentGraph,
        transcript: list,
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
        self,
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
        modified_graph = self.apply_fix_to_graph(graph, changes)
        result = await self._execution.run_test(modified_graph, test_case, options, metrics_config)

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
            improved=self.scores_improved(original_scores, new_scores),
            original_scores=original_scores,
            new_scores=new_scores,
        )

    async def revise_fix(
        self,
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

    def apply_fix_to_graph(self, graph: AgentGraph, changes: list[PromptChange]) -> AgentGraph:
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

    def scores_improved(self, original: dict[str, float], new: dict[str, float]) -> bool:
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
