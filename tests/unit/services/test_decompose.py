"""Tests for voicetest.services.decompose module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.decompose import DecompositionPlan
from voicetest.models.decompose import HandoffRule
from voicetest.models.decompose import PromptSegment
from voicetest.models.decompose import SubAgentSpec
from voicetest.services.decompose import DecomposeService


@pytest.fixture
def service():
    return DecomposeService()


@pytest.fixture
def multi_node_graph():
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the customer warmly and ask how you can help.",
                transitions=[
                    Transition(
                        target_node_id="billing",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User has billing question"
                        ),
                    ),
                    Transition(
                        target_node_id="support",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User needs technical support"
                        ),
                    ),
                ],
            ),
            "billing": AgentNode(
                id="billing",
                state_prompt="Help the customer with billing inquiries.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Billing resolved"),
                    )
                ],
            ),
            "support": AgentNode(
                id="support",
                state_prompt="Provide technical support.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Support complete"),
                    )
                ],
            ),
            "end": AgentNode(
                id="end",
                state_prompt="Thank the customer and end the call politely.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
        source_metadata={"general_prompt": "You are a professional customer service agent."},
    )


@pytest.fixture
def monolithic_graph():
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="Handle everything.",
                transitions=[],
            ),
        },
        entry_node_id="main",
        source_type="custom",
        source_metadata={"general_prompt": "You are a scheduling assistant."},
    )


class TestBuildSubGraph:
    def test_multi_node_prunes_to_assigned_nodes(self, service, multi_node_graph):
        spec = SubAgentSpec(
            sub_agent_id="billing_agent",
            name="Billing Agent",
            description="Billing",
            node_ids=["billing", "end"],
        )
        sub_graph = service.build_sub_graph(
            multi_node_graph,
            spec,
            refined_general_prompt="You handle billing.",
            node_prompts={},
        )
        assert set(sub_graph.nodes.keys()) == {"billing", "end"}
        assert sub_graph.entry_node_id == "billing"
        assert sub_graph.source_metadata["general_prompt"] == "You handle billing."

    def test_multi_node_filters_transitions(self, service, multi_node_graph):
        spec = SubAgentSpec(
            sub_agent_id="billing_agent",
            name="Billing Agent",
            description="Billing",
            node_ids=["billing", "end"],
        )
        sub_graph = service.build_sub_graph(
            multi_node_graph,
            spec,
            refined_general_prompt="Billing prompt",
            node_prompts={},
        )
        # billing -> end transition should remain
        billing_node = sub_graph.nodes["billing"]
        assert len(billing_node.transitions) == 1
        assert billing_node.transitions[0].target_node_id == "end"

        # end has no transitions
        assert sub_graph.nodes["end"].transitions == []

    def test_multi_node_removes_out_of_scope_transitions(self, service, multi_node_graph):
        spec = SubAgentSpec(
            sub_agent_id="intake",
            name="Intake",
            description="Greeting only",
            node_ids=["greeting"],
        )
        sub_graph = service.build_sub_graph(
            multi_node_graph,
            spec,
            refined_general_prompt="You greet callers.",
            node_prompts={},
        )
        # greeting had transitions to billing and support, both pruned
        assert sub_graph.nodes["greeting"].transitions == []

    def test_applies_refined_node_prompts(self, service, multi_node_graph):
        spec = SubAgentSpec(
            sub_agent_id="billing_agent",
            name="Billing Agent",
            description="Billing",
            node_ids=["billing", "end"],
        )
        sub_graph = service.build_sub_graph(
            multi_node_graph,
            spec,
            refined_general_prompt="Billing prompt",
            node_prompts={"billing": "Handle billing including refunds and disputes."},
        )
        assert (
            sub_graph.nodes["billing"].state_prompt
            == "Handle billing including refunds and disputes."
        )
        # end node not in node_prompts, should keep original
        assert (
            sub_graph.nodes["end"].state_prompt == "Thank the customer and end the call politely."
        )

    def test_preserves_source_type(self, service, multi_node_graph):
        spec = SubAgentSpec(
            sub_agent_id="a",
            name="A",
            description="A",
            node_ids=["greeting"],
        )
        sub_graph = service.build_sub_graph(
            multi_node_graph, spec, refined_general_prompt="p", node_prompts={}
        )
        assert sub_graph.source_type == "custom"

    def test_does_not_mutate_original(self, service, multi_node_graph):
        spec = SubAgentSpec(
            sub_agent_id="billing_agent",
            name="Billing",
            description="Billing",
            node_ids=["billing", "end"],
        )
        service.build_sub_graph(
            multi_node_graph,
            spec,
            refined_general_prompt="Changed",
            node_prompts={"billing": "Changed prompt"},
        )
        # Original should be unchanged
        assert (
            multi_node_graph.source_metadata["general_prompt"]
            == "You are a professional customer service agent."
        )
        assert (
            multi_node_graph.nodes["billing"].state_prompt
            == "Help the customer with billing inquiries."
        )
        assert len(multi_node_graph.nodes) == 4

    def test_monolithic_creates_nodes_from_segments(self, service, monolithic_graph):
        spec = SubAgentSpec(
            sub_agent_id="intake",
            name="Intake",
            description="Intake flow",
            node_ids=["NEW:greeting", "NEW:id_verify"],
            prompt_segments=[
                PromptSegment(
                    sub_agent_id="intake",
                    segment_text="Greet the caller warmly.",
                    purpose="greeting",
                ),
                PromptSegment(
                    sub_agent_id="intake",
                    segment_text="Verify the caller's identity.",
                    purpose="id_verify",
                ),
            ],
        )
        sub_graph = service.build_sub_graph(
            monolithic_graph,
            spec,
            refined_general_prompt="You are an intake agent.",
            node_prompts={},
        )
        assert "greeting" in sub_graph.nodes
        assert "id_verify" in sub_graph.nodes
        assert sub_graph.nodes["greeting"].state_prompt == "Greet the caller warmly."
        assert sub_graph.nodes["id_verify"].state_prompt == "Verify the caller's identity."
        assert sub_graph.entry_node_id == "greeting"

    def test_entry_node_is_first_in_node_ids(self, service, multi_node_graph):
        spec = SubAgentSpec(
            sub_agent_id="combo",
            name="Combo",
            description="Combo",
            node_ids=["support", "end"],
        )
        sub_graph = service.build_sub_graph(
            multi_node_graph, spec, refined_general_prompt="p", node_prompts={}
        )
        assert sub_graph.entry_node_id == "support"


class TestBuildManifest:
    def test_builds_manifest_from_plan(self, service):
        plan = DecompositionPlan(
            num_sub_agents=2,
            sub_agents=[
                SubAgentSpec(
                    sub_agent_id="intake",
                    name="Intake Agent",
                    description="Handles greeting",
                    node_ids=["greeting"],
                ),
                SubAgentSpec(
                    sub_agent_id="billing",
                    name="Billing Agent",
                    description="Handles billing",
                    node_ids=["billing", "end"],
                ),
            ],
            handoff_rules=[
                HandoffRule(
                    source_sub_agent_id="intake",
                    target_sub_agent_id="billing",
                    condition="Billing question",
                ),
            ],
            rationale="Split by domain",
        )
        manifest = service.build_manifest(plan)
        assert manifest.entry_sub_agent_id == "intake"
        assert len(manifest.sub_agents) == 2
        assert manifest.sub_agents[0].filename == "intake.json"
        assert manifest.sub_agents[1].filename == "billing.json"
        assert len(manifest.handoff_rules) == 1

    def test_manifest_entry_is_first_sub_agent(self, service):
        plan = DecompositionPlan(
            num_sub_agents=1,
            sub_agents=[
                SubAgentSpec(
                    sub_agent_id="only_agent",
                    name="Only",
                    description="Solo",
                    node_ids=["a"],
                ),
            ],
            handoff_rules=[],
            rationale="Single agent",
        )
        manifest = service.build_manifest(plan)
        assert manifest.entry_sub_agent_id == "only_agent"

    def test_manifest_filenames(self, service):
        plan = DecompositionPlan(
            num_sub_agents=3,
            sub_agents=[
                SubAgentSpec(sub_agent_id="a", name="A", description="A", node_ids=["n1"]),
                SubAgentSpec(sub_agent_id="b", name="B", description="B", node_ids=["n2"]),
                SubAgentSpec(sub_agent_id="c", name="C", description="C", node_ids=["n3"]),
            ],
            handoff_rules=[],
            rationale="Three agents",
        )
        manifest = service.build_manifest(plan)
        filenames = [e.filename for e in manifest.sub_agents]
        assert filenames == ["a.json", "b.json", "c.json"]


class TestDecompose:
    @pytest.mark.asyncio
    async def test_full_pipeline_mock(self, service, multi_node_graph):
        """Full decompose pipeline using mock judge."""
        result = await service.decompose(
            multi_node_graph,
            model="openai/gpt-4o-mini",
            num_agents=0,
            _mock_plan=DecompositionPlan(
                num_sub_agents=2,
                sub_agents=[
                    SubAgentSpec(
                        sub_agent_id="intake",
                        name="Intake",
                        description="Greeting",
                        node_ids=["greeting"],
                    ),
                    SubAgentSpec(
                        sub_agent_id="billing",
                        name="Billing",
                        description="Billing + end",
                        node_ids=["billing", "end"],
                    ),
                ],
                handoff_rules=[
                    HandoffRule(
                        source_sub_agent_id="intake",
                        target_sub_agent_id="billing",
                        condition="Billing question",
                    ),
                ],
                rationale="Split by domain",
            ),
            _mock_refined_prompt="Refined prompt",
            _mock_node_prompts={},
        )
        assert result.plan.num_sub_agents == 2
        assert "intake" in result.sub_graphs
        assert "billing" in result.sub_graphs
        assert result.manifest.entry_sub_agent_id == "intake"
        assert len(result.manifest.handoff_rules) == 1

    @pytest.mark.asyncio
    async def test_sub_graphs_are_valid(self, service, multi_node_graph):
        """Each sub-graph should contain only its assigned nodes."""
        result = await service.decompose(
            multi_node_graph,
            model="openai/gpt-4o-mini",
            num_agents=0,
            _mock_plan=DecompositionPlan(
                num_sub_agents=2,
                sub_agents=[
                    SubAgentSpec(
                        sub_agent_id="intake",
                        name="Intake",
                        description="Greeting",
                        node_ids=["greeting"],
                    ),
                    SubAgentSpec(
                        sub_agent_id="ops",
                        name="Operations",
                        description="Support and billing",
                        node_ids=["billing", "support", "end"],
                    ),
                ],
                handoff_rules=[],
                rationale="test",
            ),
            _mock_refined_prompt="p",
            _mock_node_prompts={},
        )
        assert set(result.sub_graphs["intake"].nodes.keys()) == {"greeting"}
        assert set(result.sub_graphs["ops"].nodes.keys()) == {"billing", "support", "end"}
