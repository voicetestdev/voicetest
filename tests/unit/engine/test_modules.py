"""Tests for voicetest.engine.modules — structured transition formatting."""

from voicetest.engine.modules import ConversationModule
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.agent import TransitionOption


class TestFormatTransitions:
    """format_transitions returns list[TransitionOption] with correct fields."""

    def test_returns_list_of_transition_options(self):
        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Greet.",
                    transitions=[
                        Transition(
                            target_node_id="b",
                            condition=TransitionCondition(type="llm_prompt", value="go to b"),
                        )
                    ],
                ),
                "b": AgentNode(id="b", state_prompt="Help."),
            },
            entry_node_id="a",
            source_type="custom",
        )
        module = ConversationModule(graph)
        result = module.format_transitions("a")

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TransitionOption)

    def test_transition_option_fields(self):
        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Greet.",
                    transitions=[
                        Transition(
                            target_node_id="b",
                            condition=TransitionCondition(
                                type="llm_prompt", value="user wants help"
                            ),
                            description="Route to help desk",
                        )
                    ],
                ),
                "b": AgentNode(id="b", state_prompt="Help."),
            },
            entry_node_id="a",
            source_type="custom",
        )
        module = ConversationModule(graph)
        result = module.format_transitions("a")

        opt = result[0]
        assert opt.target == "b"
        assert opt.condition == "user wants help"
        assert opt.condition_type == "llm_prompt"
        assert opt.description == "Route to help desk"

    def test_condition_type_preserved(self):
        """condition_type reflects the original TransitionCondition.type."""
        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Greet.",
                    transitions=[
                        Transition(
                            target_node_id="b",
                            condition=TransitionCondition(type="always", value=""),
                        ),
                        Transition(
                            target_node_id="c",
                            condition=TransitionCondition(type="equation", value="{{age}} > 18"),
                        ),
                        Transition(
                            target_node_id="d",
                            condition=TransitionCondition(type="tool_call", value="lookup_user"),
                        ),
                    ],
                ),
                "b": AgentNode(id="b", state_prompt="B."),
                "c": AgentNode(id="c", state_prompt="C."),
                "d": AgentNode(id="d", state_prompt="D."),
            },
            entry_node_id="a",
            source_type="custom",
        )
        module = ConversationModule(graph)
        result = module.format_transitions("a")

        assert len(result) == 3
        assert result[0].condition_type == "always"
        assert result[1].condition_type == "equation"
        assert result[2].condition_type == "tool_call"

    def test_empty_condition_value_uses_fallback(self):
        """Empty condition.value becomes 'No condition specified'."""
        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Greet.",
                    transitions=[
                        Transition(
                            target_node_id="b",
                            condition=TransitionCondition(type="always", value=""),
                        )
                    ],
                ),
                "b": AgentNode(id="b", state_prompt="B."),
            },
            entry_node_id="a",
            source_type="custom",
        )
        module = ConversationModule(graph)
        result = module.format_transitions("a")

        assert result[0].condition == "No condition specified"

    def test_returns_empty_list_for_no_transitions(self):
        graph = AgentGraph(
            nodes={
                "a": AgentNode(id="a", state_prompt="Greet.", transitions=[]),
            },
            entry_node_id="a",
            source_type="custom",
        )
        module = ConversationModule(graph)
        result = module.format_transitions("a")

        assert result == []

    def test_returns_empty_list_for_unknown_node(self):
        graph = AgentGraph(
            nodes={
                "a": AgentNode(id="a", state_prompt="Greet.", transitions=[]),
            },
            entry_node_id="a",
            source_type="custom",
        )
        module = ConversationModule(graph)
        result = module.format_transitions("nonexistent")

        assert result == []

    def test_description_none_when_not_set(self):
        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Greet.",
                    transitions=[
                        Transition(
                            target_node_id="b",
                            condition=TransitionCondition(type="llm_prompt", value="go to b"),
                        )
                    ],
                ),
                "b": AgentNode(id="b", state_prompt="Help."),
            },
            entry_node_id="a",
            source_type="custom",
        )
        module = ConversationModule(graph)
        result = module.format_transitions("a")

        assert result[0].description is None
