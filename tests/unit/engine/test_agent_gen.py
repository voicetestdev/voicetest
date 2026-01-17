"""Tests for voicetest.engine.agent_gen module."""

import pytest

from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    Transition,
    TransitionCondition,
)


@pytest.fixture
def simple_graph() -> AgentGraph:
    """Create a simple two-node graph for testing."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                instructions="Greet the user warmly.",
                transitions=[
                    Transition(
                        target_node_id="farewell",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User wants to end the conversation"
                        ),
                    )
                ],
            ),
            "farewell": AgentNode(
                id="farewell", instructions="Say goodbye politely.", transitions=[]
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


@pytest.fixture
def multi_branch_graph() -> AgentGraph:
    """Create a graph with multiple branches."""
    return AgentGraph(
        nodes={
            "start": AgentNode(
                id="start",
                instructions="Welcome the user. Ask what they need help with.",
                transitions=[
                    Transition(
                        target_node_id="billing",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User has billing questions"
                        ),
                    ),
                    Transition(
                        target_node_id="support",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User has technical issues"
                        ),
                    ),
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="User is done"),
                    ),
                ],
            ),
            "billing": AgentNode(
                id="billing",
                instructions="Help with billing inquiries.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Issue resolved"),
                    )
                ],
            ),
            "support": AgentNode(
                id="support",
                instructions="Provide technical support.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Issue resolved"),
                    )
                ],
            ),
            "end": AgentNode(
                id="end", instructions="Thank the user and end the call.", transitions=[]
            ),
        },
        entry_node_id="start",
        source_type="custom",
    )


class TestAgentGenerator:
    """Tests for agent class generation."""

    def test_generate_agent_classes_returns_dict(self, simple_graph):
        from voicetest.engine.agent_gen import generate_agent_classes

        result = generate_agent_classes(simple_graph)

        assert isinstance(result, dict)
        assert "greeting" in result
        assert "farewell" in result

    def test_generated_class_count_matches_nodes(self, multi_branch_graph):
        from voicetest.engine.agent_gen import generate_agent_classes

        result = generate_agent_classes(multi_branch_graph)

        assert len(result) == 4  # start, billing, support, end

    def test_generated_agent_has_instructions(self, simple_graph):
        from voicetest.engine.agent_gen import generate_agent_classes

        classes = generate_agent_classes(simple_graph)
        greeting_class = classes["greeting"]

        # Instantiate to check instructions
        agent = greeting_class()
        assert "Greet" in agent.instructions

    def test_generated_agent_has_node_id(self, simple_graph):
        from voicetest.engine.agent_gen import generate_agent_classes

        classes = generate_agent_classes(simple_graph)
        greeting_class = classes["greeting"]

        assert greeting_class._node_id == "greeting"

    def test_generated_agent_has_transition_tools(self, simple_graph):
        from voicetest.engine.agent_gen import generate_agent_classes

        classes = generate_agent_classes(simple_graph)
        greeting_class = classes["greeting"]
        agent = greeting_class()

        # Should have one transition tool
        assert len(agent._transition_tools) == 1

    def test_transition_tool_has_correct_docstring(self, simple_graph):
        from voicetest.engine.agent_gen import generate_agent_classes

        classes = generate_agent_classes(simple_graph)
        greeting_class = classes["greeting"]
        agent = greeting_class()

        # Tool docstring should contain the condition
        tool = agent._transition_tools[0]
        assert "end the conversation" in tool.__doc__.lower()

    def test_node_without_transitions_has_no_tools(self, simple_graph):
        from voicetest.engine.agent_gen import generate_agent_classes

        classes = generate_agent_classes(simple_graph)
        farewell_class = classes["farewell"]
        agent = farewell_class()

        assert len(agent._transition_tools) == 0

    def test_multi_branch_node_has_multiple_tools(self, multi_branch_graph):
        from voicetest.engine.agent_gen import generate_agent_classes

        classes = generate_agent_classes(multi_branch_graph)
        start_class = classes["start"]
        agent = start_class()

        # Start node has 3 transitions
        assert len(agent._transition_tools) == 3
