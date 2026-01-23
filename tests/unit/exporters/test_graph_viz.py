"""Tests for voicetest.exporters.graph_viz module."""

import pytest

from voicetest.exporters.graph_viz import export_mermaid
from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    ToolDefinition,
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
                        condition=TransitionCondition(type="llm_prompt", value="User wants to end"),
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
def graph_with_end_call() -> AgentGraph:
    """Create a graph with end_call tools for testing."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                instructions="Greet the user warmly.",
                transitions=[
                    Transition(
                        target_node_id="closing",
                        condition=TransitionCondition(type="llm_prompt", value="User satisfied"),
                    )
                ],
                tools=[
                    ToolDefinition(
                        name="end_call",
                        description="End the call when done",
                        parameters={},
                    )
                ],
            ),
            "closing": AgentNode(
                id="closing",
                instructions="Close the conversation.",
                transitions=[],
                tools=[
                    ToolDefinition(
                        name="end_call",
                        description="End the call politely",
                        parameters={},
                    )
                ],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


class TestExportMermaid:
    """Tests for export_mermaid function."""

    def test_basic_graph_export(self, simple_graph):
        """Test basic mermaid export."""
        result = export_mermaid(simple_graph)

        assert "flowchart TD" in result
        assert "greeting" in result
        assert "farewell" in result

    def test_includes_node_labels(self, simple_graph):
        """Test that node labels are included."""
        result = export_mermaid(simple_graph)

        assert "Greet the user" in result
        assert "Say goodbye" in result

    def test_includes_transitions(self, simple_graph):
        """Test that transitions are included."""
        result = export_mermaid(simple_graph)

        assert "greeting -->" in result
        assert "farewell" in result

    def test_entry_node_styled_green(self, simple_graph):
        """Test that entry node has green styling."""
        result = export_mermaid(simple_graph)

        assert "style greeting fill:#16a34a" in result

    def test_long_instructions_truncated(self):
        """Test that long instructions are truncated."""
        graph = AgentGraph(
            nodes={
                "verbose": AgentNode(
                    id="verbose",
                    instructions="A" * 100,  # Very long instructions
                    transitions=[],
                )
            },
            entry_node_id="verbose",
            source_type="custom",
        )

        result = export_mermaid(graph)

        # Should be truncated with ...
        assert "..." in result
        # Should not contain full 100 A's
        assert "A" * 100 not in result


class TestMermaidEndCallNode:
    """Tests for end_call node in mermaid export."""

    def test_end_call_node_added(self, graph_with_end_call):
        """Test that end_call node is added when tools exist."""
        result = export_mermaid(graph_with_end_call)

        assert 'end_call(("End Call"))' in result

    def test_end_call_edges_from_nodes_with_tool(self, graph_with_end_call):
        """Test that edges to end_call are added from nodes with end_call tool."""
        result = export_mermaid(graph_with_end_call)

        assert "greeting -->" in result
        assert "end_call" in result
        # Both greeting and closing have end_call tool
        assert result.count("| end_call") == 2

    def test_end_call_node_styled_red(self, graph_with_end_call):
        """Test that end_call node has red styling."""
        result = export_mermaid(graph_with_end_call)

        assert "style end_call fill:#dc2626" in result

    def test_no_end_call_node_without_tools(self, simple_graph):
        """Test that end_call node is not added when no end_call tools exist."""
        result = export_mermaid(simple_graph)

        assert "end_call" not in result

    def test_end_call_edge_includes_description(self, graph_with_end_call):
        """Test that end_call edge includes tool description."""
        result = export_mermaid(graph_with_end_call)

        # Description should be in the edge label
        assert "End the call" in result
