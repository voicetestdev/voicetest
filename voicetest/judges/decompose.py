"""Decompose judge for splitting agent graphs into sub-agents."""

import json
import logging

import dspy

from voicetest.llm import call_llm
from voicetest.models.agent import AgentGraph
from voicetest.models.decompose import DecompositionPlan
from voicetest.models.decompose import HandoffRule
from voicetest.models.decompose import SubAgentSpec
from voicetest.retry import OnErrorCallback


logger = logging.getLogger(__name__)


class AnalyzeGraphSignature(dspy.Signature):
    """Analyze a voice agent graph and propose a decomposition into sub-agents.

    Examine the graph structure, prompts, and transitions to identify logical
    groupings of nodes that form coherent sub-agents. Determine handoff
    conditions between them.
    """

    graph_structure: str = dspy.InputField(
        desc="Full agent graph with prompt texts, node definitions, and transitions"
    )
    num_nodes: int = dspy.InputField(desc="Total number of nodes in the graph")
    is_monolithic: bool = dspy.InputField(
        desc="Whether the graph is a single-node monolithic prompt"
    )
    requested_num_agents: int = dspy.InputField(
        desc="Requested number of sub-agents (0 = decide automatically)"
    )

    num_sub_agents: int = dspy.OutputField(desc="Number of sub-agents to create")
    sub_agents: str = dspy.OutputField(
        desc=(
            "JSON array of sub-agent specs. Each object has: "
            "sub_agent_id, name, description, node_ids (list of existing node IDs "
            "or NEW:<purpose> for monolithic graphs), "
            "prompt_segments (optional, for monolithic: "
            "list of {sub_agent_id, segment_text, purpose})"
        )
    )
    handoff_rules: str = dspy.OutputField(
        desc=(
            "JSON array of handoff rules. Each object has: "
            "source_sub_agent_id, target_sub_agent_id, condition, description (optional)"
        )
    )
    rationale: str = dspy.OutputField(desc="Explanation of why this decomposition was chosen")


class RefineSubAgentSignature(dspy.Signature):
    """Refine prompts for a sub-agent so it works independently.

    Distribute relevant context from the general prompt into this sub-agent's
    prompts. Adjust state prompts so they make sense without the other nodes.
    """

    original_graph_structure: str = dspy.InputField(desc="Full original agent graph for context")
    sub_agent_spec: str = dspy.InputField(
        desc="JSON spec of this sub-agent (id, name, description, node_ids)"
    )
    original_general_prompt: str = dspy.InputField(
        desc="The original general prompt from the full agent"
    )

    refined_general_prompt: str = dspy.OutputField(desc="Refined general prompt for this sub-agent")
    node_prompts: str = dspy.OutputField(
        desc="JSON object mapping node_id to refined state_prompt text"
    )


class DecomposeJudge:
    """Analyze agent graphs and propose decompositions into sub-agents.

    Uses LLM to identify logical groupings and refine prompts for
    independent operation.
    """

    def __init__(self, model: str):
        self.model = model

        # Mock mode for testing without LLM calls
        self._mock_mode = False
        self._mock_plan: DecompositionPlan | None = None
        self._mock_refined_prompt: str | None = None
        self._mock_node_prompts: dict[str, str] | None = None

    async def analyze_graph(
        self,
        graph: AgentGraph,
        requested_num_agents: int = 0,
        on_error: OnErrorCallback | None = None,
    ) -> DecompositionPlan:
        """Analyze the graph and propose a decomposition plan."""
        if self._mock_mode and self._mock_plan:
            return self._mock_plan

        formatted_graph = self._format_graph_full(graph)
        is_monolithic = len(graph.nodes) <= 1

        result = await call_llm(
            self.model,
            AnalyzeGraphSignature,
            on_error=on_error,
            graph_structure=formatted_graph,
            num_nodes=len(graph.nodes),
            is_monolithic=is_monolithic,
            requested_num_agents=requested_num_agents,
        )

        return self._parse_plan(
            num_sub_agents=int(result.num_sub_agents),
            sub_agents_raw=result.sub_agents,
            handoff_rules_raw=result.handoff_rules,
            rationale=result.rationale,
        )

    async def refine_sub_agent(
        self,
        graph: AgentGraph,
        sub_agent_spec: SubAgentSpec,
        on_error: OnErrorCallback | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Refine prompts for a sub-agent to work independently.

        Returns:
            Tuple of (refined_general_prompt, {node_id: refined_state_prompt}).
        """
        if self._mock_mode:
            return (
                self._mock_refined_prompt or "",
                self._mock_node_prompts or {},
            )

        formatted_graph = self._format_graph_full(graph)
        original_general = graph.source_metadata.get("general_prompt", "")

        result = await call_llm(
            self.model,
            RefineSubAgentSignature,
            on_error=on_error,
            original_graph_structure=formatted_graph,
            sub_agent_spec=json.dumps(sub_agent_spec.model_dump()),
            original_general_prompt=original_general,
        )

        node_prompts = self._parse_node_prompts(result.node_prompts)
        return result.refined_general_prompt, node_prompts

    def _format_graph_full(self, graph: AgentGraph) -> str:
        """Format the agent graph with full prompt texts for analysis."""
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

    def _parse_plan(
        self,
        num_sub_agents: int,
        sub_agents_raw: str,
        handoff_rules_raw: str,
        rationale: str,
    ) -> DecompositionPlan:
        """Parse LLM output into a DecompositionPlan."""
        sub_agents = self._parse_sub_agents(sub_agents_raw)
        handoff_rules = self._parse_handoff_rules(handoff_rules_raw)

        return DecompositionPlan(
            num_sub_agents=num_sub_agents,
            sub_agents=sub_agents,
            handoff_rules=handoff_rules,
            rationale=rationale,
        )

    def _parse_sub_agents(self, raw: str) -> list[SubAgentSpec]:
        """Parse sub-agent specs from LLM JSON output."""
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                data = [data]
            return [SubAgentSpec.model_validate(item) for item in data]
        except (json.JSONDecodeError, Exception):
            logger.warning("Failed to parse sub-agent specs: %s", raw[:200])
            return []

    def _parse_handoff_rules(self, raw: str) -> list[HandoffRule]:
        """Parse handoff rules from LLM JSON output."""
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                data = [data]
            return [HandoffRule.model_validate(item) for item in data]
        except (json.JSONDecodeError, Exception):
            logger.warning("Failed to parse handoff rules: %s", raw[:200])
            return []

    def _parse_node_prompts(self, raw: str) -> dict[str, str]:
        """Parse node prompts from LLM JSON output."""
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return {}
            return {str(k): str(v) for k, v in data.items()}
        except (json.JSONDecodeError, Exception):
            logger.warning("Failed to parse node prompts: %s", raw[:200])
            return {}
