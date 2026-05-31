"""Shared fixtures for exporter tests."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import NodeType
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


@pytest.fixture
def three_node_graph() -> AgentGraph:
    """Three-node graph (greeting → help → closing) for exporter tests."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user warmly.",
                transitions=[
                    Transition(
                        target_node_id="help",
                        condition=TransitionCondition(
                            type="llm_prompt",
                            value="User needs help with something",
                        ),
                    ),
                ],
                node_type=NodeType.CONVERSATION,
            ),
            "help": AgentNode(
                id="help",
                state_prompt="Help the user with their request.",
                transitions=[
                    Transition(
                        target_node_id="closing",
                        condition=TransitionCondition(
                            type="llm_prompt",
                            value="User request is complete",
                        ),
                    ),
                ],
                node_type=NodeType.CONVERSATION,
            ),
            "closing": AgentNode(
                id="closing",
                state_prompt="Thank the user and end the conversation.",
                transitions=[],
                node_type=NodeType.CONVERSATION,
            ),
        },
        entry_node_id="greeting",
        source_type="test",
    )
