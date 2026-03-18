"""Tests for voicetest.engine.modules — structured transition formatting."""

from voicetest.engine.modules import ConversationModule
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import GlobalNodeSetting
from voicetest.models.agent import GoBackCondition
from voicetest.models.agent import NodeType
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

        # always-type transitions are excluded (auto-fire, not LLM-decided)
        assert len(result) == 2
        assert result[0].condition_type == "equation"
        assert result[1].condition_type == "tool_call"

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

        # always-type transitions are excluded from LLM options
        assert result == []

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


class TestGlobalNodeTransitions:
    """Tests for global node conditions in format_transitions."""

    def _make_graph_with_global(self):
        """Build a graph with one global node for testing."""
        return AgentGraph(
            nodes={
                "greeting": AgentNode(
                    id="greeting",
                    state_prompt="Greet.",
                    transitions=[
                        Transition(
                            target_node_id="order",
                            condition=TransitionCondition(
                                type="llm_prompt", value="Caller wants to order"
                            ),
                        )
                    ],
                ),
                "order": AgentNode(
                    id="order",
                    state_prompt="Take order.",
                    transitions=[],
                ),
                "cancel": AgentNode(
                    id="cancel",
                    state_prompt="Ask about cancellation.",
                    transitions=[],
                    global_node_setting=GlobalNodeSetting(
                        condition="Caller wants to cancel",
                        go_back_conditions=[
                            GoBackCondition(
                                id="gb-1",
                                condition=TransitionCondition(
                                    type="llm_prompt",
                                    value="Caller wants to continue",
                                ),
                            ),
                        ],
                    ),
                ),
            },
            entry_node_id="greeting",
            source_type="retell",
        )

    def test_global_conditions_appended_to_conversation_node(self):
        graph = self._make_graph_with_global()
        module = ConversationModule(graph)
        result = module.format_transitions("greeting")

        # 1 local transition + 1 global entry condition
        assert len(result) == 2
        global_opt = result[1]
        assert global_opt.target == "cancel"
        assert global_opt.condition == "Caller wants to cancel"
        assert global_opt.condition_type == "llm_prompt"

    def test_global_conditions_appended_to_node_without_local_transitions(self):
        graph = self._make_graph_with_global()
        module = ConversationModule(graph)
        result = module.format_transitions("order")

        # 0 local transitions + 1 global entry condition
        assert len(result) == 1
        assert result[0].target == "cancel"

    def test_global_conditions_not_appended_to_non_conversation_nodes(self):
        graph = AgentGraph(
            nodes={
                "router": AgentNode(
                    id="router",
                    state_prompt="",
                    node_type=NodeType.LOGIC,
                    transitions=[
                        Transition(
                            target_node_id="a",
                            condition=TransitionCondition(type="equation", value="x == 1"),
                        ),
                    ],
                ),
                "a": AgentNode(id="a", state_prompt="A."),
                "cancel": AgentNode(
                    id="cancel",
                    state_prompt="Cancel.",
                    global_node_setting=GlobalNodeSetting(
                        condition="Caller wants to cancel",
                    ),
                ),
            },
            entry_node_id="router",
            source_type="retell",
        )
        module = ConversationModule(graph)
        result = module.format_transitions("router")

        # Only the equation transition, no global
        assert len(result) == 1
        assert result[0].target == "a"

    def test_no_self_transition_for_global_node(self):
        graph = self._make_graph_with_global()
        module = ConversationModule(graph)
        result = module.format_transitions("cancel")

        # Should not include cancel -> cancel
        targets = {opt.target for opt in result}
        assert "cancel" not in targets

    def test_go_back_conditions_included_when_originator_set(self):
        graph = self._make_graph_with_global()
        module = ConversationModule(graph)
        result = module.format_transitions("cancel", originator_id="greeting")

        # Go-back condition should target the originator
        go_back_opts = [opt for opt in result if opt.target == "greeting"]
        assert len(go_back_opts) == 1
        assert "continue" in go_back_opts[0].condition.lower()

    def test_go_back_conditions_absent_without_originator(self):
        graph = self._make_graph_with_global()
        module = ConversationModule(graph)
        result = module.format_transitions("cancel")

        # No go-back since no originator
        targets = {opt.target for opt in result}
        assert "greeting" not in targets

    def test_zero_global_nodes_unchanged_behavior(self):
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

        assert len(result) == 1
        assert result[0].target == "b"
