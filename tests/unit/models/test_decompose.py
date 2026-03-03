"""Tests for decomposition data models."""

from voicetest.models.agent import AgentGraph
from voicetest.models.decompose import DecompositionPlan
from voicetest.models.decompose import DecompositionResult
from voicetest.models.decompose import HandoffRule
from voicetest.models.decompose import NodeAssignment
from voicetest.models.decompose import OrchestratorManifest
from voicetest.models.decompose import PromptSegment
from voicetest.models.decompose import SubAgentManifestEntry
from voicetest.models.decompose import SubAgentSpec


class TestNodeAssignment:
    def test_basic(self):
        na = NodeAssignment(
            node_id="greeting",
            sub_agent_id="intake",
            rationale="Greeting belongs to intake flow",
        )
        assert na.node_id == "greeting"
        assert na.sub_agent_id == "intake"

    def test_serialization_roundtrip(self):
        na = NodeAssignment(
            node_id="billing",
            sub_agent_id="billing_agent",
            rationale="Billing node clusters with billing agent",
        )
        data = na.model_dump()
        restored = NodeAssignment.model_validate(data)
        assert restored == na


class TestPromptSegment:
    def test_basic(self):
        seg = PromptSegment(
            sub_agent_id="intake",
            segment_text="Greet the caller and collect their name.",
            purpose="identity_collection",
        )
        assert seg.sub_agent_id == "intake"
        assert "Greet" in seg.segment_text

    def test_serialization_roundtrip(self):
        seg = PromptSegment(
            sub_agent_id="scheduling",
            segment_text="Schedule an appointment.",
            purpose="appointment_booking",
        )
        data = seg.model_dump()
        restored = PromptSegment.model_validate(data)
        assert restored == seg


class TestSubAgentSpec:
    def test_multi_node(self):
        spec = SubAgentSpec(
            sub_agent_id="billing_agent",
            name="Billing Agent",
            description="Handles billing inquiries",
            node_ids=["billing", "payment"],
        )
        assert spec.sub_agent_id == "billing_agent"
        assert len(spec.node_ids) == 2
        assert spec.prompt_segments == []

    def test_monolithic_with_segments(self):
        spec = SubAgentSpec(
            sub_agent_id="intake",
            name="Intake Agent",
            description="Handles intake",
            node_ids=["NEW:greeting", "NEW:id_verification"],
            prompt_segments=[
                PromptSegment(
                    sub_agent_id="intake",
                    segment_text="Greet caller",
                    purpose="greeting",
                ),
            ],
        )
        assert len(spec.prompt_segments) == 1
        assert spec.node_ids[0].startswith("NEW:")

    def test_serialization_roundtrip(self):
        spec = SubAgentSpec(
            sub_agent_id="support",
            name="Support Agent",
            description="Technical support",
            node_ids=["support", "escalation"],
            prompt_segments=[
                PromptSegment(
                    sub_agent_id="support",
                    segment_text="Troubleshoot",
                    purpose="troubleshooting",
                ),
            ],
        )
        data = spec.model_dump()
        restored = SubAgentSpec.model_validate(data)
        assert restored == spec


class TestHandoffRule:
    def test_basic(self):
        rule = HandoffRule(
            source_sub_agent_id="intake",
            target_sub_agent_id="billing",
            condition="Customer mentions billing or payment",
            description="Route to billing agent",
        )
        assert rule.source_sub_agent_id == "intake"
        assert rule.target_sub_agent_id == "billing"

    def test_no_description(self):
        rule = HandoffRule(
            source_sub_agent_id="a",
            target_sub_agent_id="b",
            condition="always",
        )
        assert rule.description is None

    def test_serialization_roundtrip(self):
        rule = HandoffRule(
            source_sub_agent_id="intake",
            target_sub_agent_id="support",
            condition="Technical issue detected",
            description="Handoff to tech support",
        )
        data = rule.model_dump()
        restored = HandoffRule.model_validate(data)
        assert restored == rule


class TestDecompositionPlan:
    def test_basic(self):
        plan = DecompositionPlan(
            num_sub_agents=2,
            sub_agents=[
                SubAgentSpec(
                    sub_agent_id="intake",
                    name="Intake",
                    description="Intake flow",
                    node_ids=["greeting"],
                ),
                SubAgentSpec(
                    sub_agent_id="billing",
                    name="Billing",
                    description="Billing flow",
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
            rationale="Split by functional domain",
        )
        assert plan.num_sub_agents == 2
        assert len(plan.sub_agents) == 2
        assert len(plan.handoff_rules) == 1

    def test_serialization_roundtrip(self):
        plan = DecompositionPlan(
            num_sub_agents=1,
            sub_agents=[
                SubAgentSpec(
                    sub_agent_id="main",
                    name="Main",
                    description="Only agent",
                    node_ids=["a"],
                ),
            ],
            handoff_rules=[],
            rationale="Single agent, no split needed",
        )
        data = plan.model_dump()
        restored = DecompositionPlan.model_validate(data)
        assert restored == plan


class TestSubAgentManifestEntry:
    def test_basic(self):
        entry = SubAgentManifestEntry(
            sub_agent_id="intake",
            name="Intake Agent",
            description="Handles intake",
            filename="intake.json",
        )
        assert entry.filename == "intake.json"

    def test_serialization_roundtrip(self):
        entry = SubAgentManifestEntry(
            sub_agent_id="billing",
            name="Billing Agent",
            description="Billing",
            filename="billing.json",
        )
        data = entry.model_dump()
        restored = SubAgentManifestEntry.model_validate(data)
        assert restored == entry


class TestOrchestratorManifest:
    def test_basic(self):
        manifest = OrchestratorManifest(
            entry_sub_agent_id="intake",
            sub_agents=[
                SubAgentManifestEntry(
                    sub_agent_id="intake",
                    name="Intake",
                    description="Intake flow",
                    filename="intake.json",
                ),
                SubAgentManifestEntry(
                    sub_agent_id="billing",
                    name="Billing",
                    description="Billing flow",
                    filename="billing.json",
                ),
            ],
            handoff_rules=[
                HandoffRule(
                    source_sub_agent_id="intake",
                    target_sub_agent_id="billing",
                    condition="Billing question",
                ),
            ],
        )
        assert manifest.entry_sub_agent_id == "intake"
        assert len(manifest.sub_agents) == 2

    def test_serialization_roundtrip(self):
        manifest = OrchestratorManifest(
            entry_sub_agent_id="main",
            sub_agents=[
                SubAgentManifestEntry(
                    sub_agent_id="main",
                    name="Main",
                    description="Main agent",
                    filename="main.json",
                ),
            ],
            handoff_rules=[],
        )
        data = manifest.model_dump()
        restored = OrchestratorManifest.model_validate(data)
        assert restored == manifest


class TestDecompositionResult:
    def test_basic(self):
        from voicetest.models.agent import AgentNode

        sub_graph = AgentGraph(
            nodes={
                "greeting": AgentNode(
                    id="greeting",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="greeting",
            source_type="custom",
        )
        plan = DecompositionPlan(
            num_sub_agents=1,
            sub_agents=[
                SubAgentSpec(
                    sub_agent_id="main",
                    name="Main",
                    description="Only agent",
                    node_ids=["greeting"],
                ),
            ],
            handoff_rules=[],
            rationale="Single agent",
        )
        manifest = OrchestratorManifest(
            entry_sub_agent_id="main",
            sub_agents=[
                SubAgentManifestEntry(
                    sub_agent_id="main",
                    name="Main",
                    description="Only agent",
                    filename="main.json",
                ),
            ],
            handoff_rules=[],
        )
        result = DecompositionResult(
            plan=plan,
            sub_graphs={"main": sub_graph},
            manifest=manifest,
        )
        assert result.plan.num_sub_agents == 1
        assert "main" in result.sub_graphs
        assert result.manifest.entry_sub_agent_id == "main"

    def test_serialization_roundtrip(self):
        from voicetest.models.agent import AgentNode

        sub_graph = AgentGraph(
            nodes={
                "n1": AgentNode(id="n1", state_prompt="Node 1", transitions=[]),
            },
            entry_node_id="n1",
            source_type="custom",
        )
        plan = DecompositionPlan(
            num_sub_agents=1,
            sub_agents=[
                SubAgentSpec(
                    sub_agent_id="agent1",
                    name="Agent 1",
                    description="First agent",
                    node_ids=["n1"],
                ),
            ],
            handoff_rules=[],
            rationale="Test",
        )
        manifest = OrchestratorManifest(
            entry_sub_agent_id="agent1",
            sub_agents=[
                SubAgentManifestEntry(
                    sub_agent_id="agent1",
                    name="Agent 1",
                    description="First agent",
                    filename="agent1.json",
                ),
            ],
            handoff_rules=[],
        )
        result = DecompositionResult(
            plan=plan,
            sub_graphs={"agent1": sub_graph},
            manifest=manifest,
        )
        data = result.model_dump()
        restored = DecompositionResult.model_validate(data)
        assert restored == result
