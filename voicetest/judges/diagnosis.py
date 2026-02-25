"""Diagnosis judge for post-run failure analysis and fix suggestion."""

import json
import logging

import dspy

from voicetest.llm import call_llm
from voicetest.models.agent import AgentGraph
from voicetest.models.diagnosis import Diagnosis
from voicetest.models.diagnosis import FaultLocation
from voicetest.models.diagnosis import FixSuggestion
from voicetest.models.diagnosis import PromptChange
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.retry import OnErrorCallback


logger = logging.getLogger(__name__)


class DiagnoseFailureSignature(dspy.Signature):
    """Diagnose why a voice agent test failed by analyzing the graph, transcript, and metrics.

    Identify WHERE in the multi-prompt system (general prompt, node state prompts,
    transitions) the failure originates, and WHY — citing specific prompt text
    and graph structure.
    """

    graph_structure: str = dspy.InputField(
        desc="Full agent graph with prompt texts, node definitions, and transitions"
    )
    transcript: str = dspy.InputField(
        desc="Conversation transcript with node_id annotations per message"
    )
    nodes_visited: list[str] = dspy.InputField(desc="Sequence of node IDs the agent traversed")
    failed_metrics: str = dspy.InputField(
        desc="Failed metric evaluations with scores, thresholds, and reasoning"
    )
    test_scenario: str = dspy.InputField(
        desc="The user prompt / test scenario that was being tested"
    )

    root_cause: str = dspy.OutputField(desc="Root cause of the test failure in 1-2 sentences")
    fault_locations: str = dspy.OutputField(
        desc=(
            "JSON array of fault locations. Each object has: "
            "location_type (general_prompt|node_prompt|transition|missing_transition), "
            "node_id (optional), transition_target_id (optional), "
            "relevant_text (exact text from the prompt), explanation"
        )
    )
    transcript_evidence: str = dspy.OutputField(
        desc="Quoted transcript lines that demonstrate the failure"
    )


class SuggestFixSignature(dspy.Signature):
    """Suggest concrete prompt and transition text changes to fix a diagnosed failure.

    Given the diagnosis, propose minimal text changes that would resolve the issue.
    Only suggest changes to text content — do not add or remove graph edges.
    """

    graph_structure: str = dspy.InputField(
        desc="Full agent graph with prompt texts, node definitions, and transitions"
    )
    diagnosis_summary: str = dspy.InputField(
        desc="Root cause analysis and fault locations from diagnosis"
    )
    failed_metrics: str = dspy.InputField(
        desc="Failed metric evaluations with scores, thresholds, and reasoning"
    )

    changes: str = dspy.OutputField(
        desc=(
            "JSON array of changes. Each object has: "
            "location_type (general_prompt|node_prompt|transition), "
            "node_id (optional), transition_target_id (optional), "
            "original_text (exact current text), proposed_text, rationale"
        )
    )
    summary: str = dspy.OutputField(desc="Brief summary of all proposed changes")
    confidence: float = dspy.OutputField(desc="Confidence that changes will fix the issue, 0.0-1.0")


class ReviseFixSignature(dspy.Signature):
    """Revise a previous fix attempt based on metric results after application.

    The previous fix was applied but did not fully resolve the issue.
    Analyze what improved, what didn't, and propose revised changes.
    """

    graph_structure: str = dspy.InputField(
        desc="Current agent graph (after previous fix was applied)"
    )
    original_diagnosis: str = dspy.InputField(desc="Original root cause analysis")
    previous_changes: str = dspy.InputField(
        desc="JSON array of changes that were previously applied"
    )
    previous_metric_results: str = dspy.InputField(
        desc="Metric results after applying previous changes"
    )

    changes: str = dspy.OutputField(
        desc=(
            "JSON array of revised changes. Each object has: "
            "location_type (general_prompt|node_prompt|transition), "
            "node_id (optional), transition_target_id (optional), "
            "original_text (exact current text), proposed_text, rationale"
        )
    )
    summary: str = dspy.OutputField(desc="Brief summary of revised changes")
    confidence: float = dspy.OutputField(
        desc="Confidence that revised changes will fix the issue, 0.0-1.0"
    )


class DiagnosisJudge:
    """Diagnose test failures and suggest prompt/transition fixes.

    Uses LLM to analyze why a test failed and propose concrete text
    changes to the agent graph that would resolve the issue.
    """

    def __init__(self, model: str):
        self.model = model

        # Mock mode for testing without LLM calls
        self._mock_mode = False
        self._mock_diagnosis: Diagnosis | None = None
        self._mock_fix: FixSuggestion | None = None

    async def diagnose(
        self,
        graph: AgentGraph,
        transcript: list[Message],
        nodes_visited: list[str],
        failed_metrics: list[MetricResult],
        test_scenario: str,
        on_error: OnErrorCallback | None = None,
    ) -> Diagnosis:
        """Diagnose where and why a test failed."""
        if self._mock_mode and self._mock_diagnosis:
            return self._mock_diagnosis

        formatted_graph = self._format_graph_full(graph)
        formatted_transcript = self._format_transcript_with_nodes(transcript)
        formatted_metrics = self._format_failed_metrics(failed_metrics)

        result = await call_llm(
            self.model,
            DiagnoseFailureSignature,
            on_error=on_error,
            graph_structure=formatted_graph,
            transcript=formatted_transcript,
            nodes_visited=nodes_visited,
            failed_metrics=formatted_metrics,
            test_scenario=test_scenario,
        )

        fault_locations = self._parse_fault_locations(result.fault_locations)

        return Diagnosis(
            fault_locations=fault_locations,
            root_cause=result.root_cause,
            transcript_evidence=result.transcript_evidence,
        )

    async def suggest_fix(
        self,
        graph: AgentGraph,
        diagnosis: Diagnosis,
        failed_metrics: list[MetricResult],
        on_error: OnErrorCallback | None = None,
    ) -> FixSuggestion:
        """Suggest concrete text changes to fix a diagnosed issue."""
        if self._mock_mode and self._mock_fix:
            return self._mock_fix

        formatted_graph = self._format_graph_full(graph)
        formatted_metrics = self._format_failed_metrics(failed_metrics)

        diagnosis_summary = f"Root cause: {diagnosis.root_cause}\nFault locations:\n"
        for loc in diagnosis.fault_locations:
            diagnosis_summary += (
                f"  - [{loc.location_type}]"
                f"{f' node={loc.node_id}' if loc.node_id else ''}"
                f": {loc.explanation}\n"
            )

        result = await call_llm(
            self.model,
            SuggestFixSignature,
            on_error=on_error,
            graph_structure=formatted_graph,
            diagnosis_summary=diagnosis_summary,
            failed_metrics=formatted_metrics,
        )

        changes = self._parse_changes(result.changes)

        return FixSuggestion(
            changes=changes,
            summary=result.summary,
            confidence=float(result.confidence),
        )

    async def revise_fix(
        self,
        graph: AgentGraph,
        diagnosis: Diagnosis,
        prev_changes: list[PromptChange],
        new_metrics: list[MetricResult],
        on_error: OnErrorCallback | None = None,
    ) -> FixSuggestion:
        """Revise a previous fix based on new metric results."""
        if self._mock_mode and self._mock_fix:
            return self._mock_fix

        formatted_graph = self._format_graph_full(graph)
        prev_changes_json = json.dumps([c.model_dump() for c in prev_changes])
        formatted_metrics = self._format_all_metrics(new_metrics)

        result = await call_llm(
            self.model,
            ReviseFixSignature,
            on_error=on_error,
            graph_structure=formatted_graph,
            original_diagnosis=diagnosis.root_cause,
            previous_changes=prev_changes_json,
            previous_metric_results=formatted_metrics,
        )

        changes = self._parse_changes(result.changes)

        return FixSuggestion(
            changes=changes,
            summary=result.summary,
            confidence=float(result.confidence),
        )

    def _format_graph_full(self, graph: AgentGraph) -> str:
        """Format the agent graph with FULL prompt texts for diagnosis."""
        lines = []

        general_prompt = graph.source_metadata.get("general_prompt")
        if general_prompt:
            lines.append("=== GENERAL PROMPT ===")
            lines.append(general_prompt)
            lines.append("")

        for node_id, node in graph.nodes.items():
            lines.append(f"=== NODE: {node_id} ===")
            lines.append(f"State Prompt: {node.state_prompt}")
            if node.transitions:
                lines.append("Transitions:")
                for t in node.transitions:
                    condition = t.condition.value or "unconditional"
                    lines.append(f"  -> {t.target_node_id}: {condition}")
            lines.append("")

        return "\n".join(lines)

    def _format_transcript_with_nodes(self, transcript: list[Message]) -> str:
        """Format transcript with node_id annotations per message."""
        if not transcript:
            return ""

        lines = []
        for msg in transcript:
            node_id = msg.metadata.get("node_id")
            prefix = f"[{node_id}] " if node_id else ""
            lines.append(f"{prefix}{msg.role.upper()}: {msg.content}")

        return "\n".join(lines)

    def _format_failed_metrics(self, metrics: list[MetricResult]) -> str:
        """Format only the failed metrics with score, threshold, and reasoning."""
        failed = [m for m in metrics if not m.passed]
        if not failed:
            return ""

        lines = []
        for m in failed:
            lines.append(
                f"FAILED: {m.metric}\n"
                f"  Score: {m.score} (threshold: {m.threshold})\n"
                f"  Reasoning: {m.reasoning}"
            )

        return "\n".join(lines)

    def _format_all_metrics(self, metrics: list[MetricResult]) -> str:
        """Format all metrics (for revision context)."""
        lines = []
        for m in metrics:
            status = "PASSED" if m.passed else "FAILED"
            lines.append(
                f"{status}: {m.metric}\n"
                f"  Score: {m.score} (threshold: {m.threshold})\n"
                f"  Reasoning: {m.reasoning}"
            )
        return "\n".join(lines)

    def _parse_fault_locations(self, raw: str) -> list[FaultLocation]:
        """Parse fault locations from LLM JSON output."""
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                data = [data]
            return [FaultLocation.model_validate(item) for item in data]
        except (json.JSONDecodeError, Exception):
            logger.warning("Failed to parse fault locations: %s", raw[:200])
            return []

    def _parse_changes(self, raw: str) -> list[PromptChange]:
        """Parse prompt changes from LLM JSON output."""
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                data = [data]
            return [PromptChange.model_validate(item) for item in data]
        except (json.JSONDecodeError, Exception):
            logger.warning("Failed to parse changes: %s", raw[:200])
            return []
