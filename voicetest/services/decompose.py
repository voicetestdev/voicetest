"""Decompose service: split agent graphs into sub-agents."""

from voicetest.judges.decompose import DecomposeJudge
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.decompose import DecompositionPlan
from voicetest.models.decompose import DecompositionResult
from voicetest.models.decompose import OrchestratorManifest
from voicetest.models.decompose import SubAgentManifestEntry
from voicetest.models.decompose import SubAgentSpec


class DecomposeService:
    """Splits an AgentGraph into M coherent sub-agents. Stateless."""

    async def decompose(
        self,
        graph: AgentGraph,
        model: str,
        num_agents: int = 0,
        *,
        _mock_plan: DecompositionPlan | None = None,
        _mock_refined_prompt: str | None = None,
        _mock_node_prompts: dict[str, str] | None = None,
    ) -> DecompositionResult:
        """Full pipeline: analyze -> refine each sub-agent -> build graphs + manifest.

        Args:
            graph: The agent graph to decompose.
            model: LLM model for analysis and refinement.
            num_agents: Requested number of sub-agents (0 = LLM decides).
            _mock_plan: For testing — bypass LLM analyze step.
            _mock_refined_prompt: For testing — bypass LLM refine step.
            _mock_node_prompts: For testing — bypass LLM refine step.

        Returns:
            DecompositionResult with plan, sub-graphs, and manifest.
        """
        judge = DecomposeJudge(model)

        if _mock_plan is not None:
            judge._mock_mode = True
            judge._mock_plan = _mock_plan
            if _mock_refined_prompt is not None:
                judge._mock_refined_prompt = _mock_refined_prompt
            if _mock_node_prompts is not None:
                judge._mock_node_prompts = _mock_node_prompts

        # Phase 1: Analyze
        plan = await judge.analyze_graph(graph, requested_num_agents=num_agents)

        # Phase 2: Refine each sub-agent
        sub_graphs: dict[str, AgentGraph] = {}
        for spec in plan.sub_agents:
            refined_general_prompt, node_prompts = await judge.refine_sub_agent(graph, spec)
            sub_graph = self.build_sub_graph(graph, spec, refined_general_prompt, node_prompts)
            sub_graphs[spec.sub_agent_id] = sub_graph

        # Phase 3: Build manifest
        manifest = self.build_manifest(plan)

        return DecompositionResult(
            plan=plan,
            sub_graphs=sub_graphs,
            manifest=manifest,
        )

    def build_sub_graph(
        self,
        graph: AgentGraph,
        spec: SubAgentSpec,
        refined_general_prompt: str,
        node_prompts: dict[str, str],
    ) -> AgentGraph:
        """Build one sub-agent's AgentGraph.

        Multi-node case: deep copy, prune to assigned nodes, filter transitions.
        Monolithic case: create nodes from prompt_segments.

        Args:
            graph: The original full agent graph.
            spec: Sub-agent specification with assigned node IDs.
            refined_general_prompt: Refined general prompt for this sub-agent.
            node_prompts: Refined state prompts for specific nodes.

        Returns:
            A sub-agent AgentGraph.
        """
        has_new_nodes = any(nid.startswith("NEW:") for nid in spec.node_ids)

        if has_new_nodes:
            return self._build_monolithic_sub_graph(spec, refined_general_prompt)

        return self._build_multi_node_sub_graph(graph, spec, refined_general_prompt, node_prompts)

    def build_manifest(self, plan: DecompositionPlan) -> OrchestratorManifest:
        """Build orchestrator manifest from plan.

        Args:
            plan: The decomposition plan.

        Returns:
            OrchestratorManifest with entry agent, sub-agent entries, and handoff rules.
        """
        entries = [
            SubAgentManifestEntry(
                sub_agent_id=sa.sub_agent_id,
                name=sa.name,
                description=sa.description,
                filename=f"{sa.sub_agent_id}.json",
            )
            for sa in plan.sub_agents
        ]

        entry_sub_agent_id = plan.sub_agents[0].sub_agent_id if plan.sub_agents else ""

        return OrchestratorManifest(
            entry_sub_agent_id=entry_sub_agent_id,
            sub_agents=entries,
            handoff_rules=plan.handoff_rules,
        )

    def _build_multi_node_sub_graph(
        self,
        graph: AgentGraph,
        spec: SubAgentSpec,
        refined_general_prompt: str,
        node_prompts: dict[str, str],
    ) -> AgentGraph:
        """Build sub-graph by pruning the original graph to assigned nodes."""
        assigned = set(spec.node_ids)
        modified = graph.model_copy(deep=True)

        # Prune to assigned nodes
        modified.nodes = {nid: node for nid, node in modified.nodes.items() if nid in assigned}

        # Filter transitions to only target assigned nodes
        for node in modified.nodes.values():
            node.transitions = [t for t in node.transitions if t.target_node_id in assigned]

        # Apply refined prompts
        modified.source_metadata = dict(modified.source_metadata)
        modified.source_metadata["general_prompt"] = refined_general_prompt

        for nid, prompt in node_prompts.items():
            if nid in modified.nodes:
                modified.nodes[nid].state_prompt = prompt

        # Set entry node to first assigned node
        modified.entry_node_id = spec.node_ids[0]

        return modified

    def _build_monolithic_sub_graph(
        self,
        spec: SubAgentSpec,
        refined_general_prompt: str,
    ) -> AgentGraph:
        """Build sub-graph from prompt segments (monolithic decomposition)."""
        nodes: dict[str, AgentNode] = {}

        for nid_raw, segment in zip(spec.node_ids, spec.prompt_segments, strict=False):
            # Strip "NEW:" prefix
            node_id = nid_raw.removeprefix("NEW:")
            nodes[node_id] = AgentNode(
                id=node_id,
                state_prompt=segment.segment_text,
                transitions=[],
            )

        # Entry node is the first
        entry = spec.node_ids[0].removeprefix("NEW:") if spec.node_ids else ""

        return AgentGraph(
            nodes=nodes,
            entry_node_id=entry,
            source_type="custom",
            source_metadata={"general_prompt": refined_general_prompt},
        )
