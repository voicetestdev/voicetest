"""Tests for voicetest.exporters.layout module."""

from voicetest.exporters.layout import compute_layout
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


def _make_graph(nodes_spec: dict, entry_node_id: str) -> AgentGraph:
    """Build an AgentGraph from a simplified spec.

    nodes_spec: {node_id: [target_id, ...], ...}
    """
    nodes = {}
    for node_id, targets in nodes_spec.items():
        transitions = [
            Transition(
                target_node_id=t,
                condition=TransitionCondition(type="llm_prompt", value=f"go to {t}"),
            )
            for t in targets
        ]
        nodes[node_id] = AgentNode(
            id=node_id,
            state_prompt=f"Prompt for {node_id}.",
            transitions=transitions,
        )
    return AgentGraph(
        nodes=nodes,
        entry_node_id=entry_node_id,
        source_type="test",
    )


class TestComputeLayout:
    """Tests for the BFS-based layout algorithm."""

    def test_linear_graph(self):
        """A->B->C gets 3 layers, each with 1 node."""
        graph = _make_graph({"A": ["B"], "B": ["C"], "C": []}, entry_node_id="A")
        positions = compute_layout(graph)

        assert len(positions) == 3
        # Each node in a distinct layer, progressing left-to-right
        assert positions["A"]["x"] < positions["B"]["x"]
        assert positions["B"]["x"] < positions["C"]["x"]

    def test_branching_graph(self):
        """A->{B,C}->D: B and C share a layer, spread vertically."""
        graph = _make_graph(
            {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []},
            entry_node_id="A",
        )
        positions = compute_layout(graph)

        assert len(positions) == 4
        # B and C at same depth (layer 1)
        assert positions["B"]["x"] == positions["C"]["x"]
        # B and C have different y positions
        assert positions["B"]["y"] != positions["C"]["y"]
        # D is one layer deeper than B/C
        assert positions["D"]["x"] > positions["B"]["x"]

    def test_single_node(self):
        """Single node placed at origin."""
        graph = _make_graph({"only": []}, entry_node_id="only")
        positions = compute_layout(graph)

        assert len(positions) == 1
        assert positions["only"]["x"] == 0
        assert positions["only"]["y"] == 0

    def test_disconnected_nodes_placed(self):
        """Nodes unreachable from entry still get positions."""
        graph = _make_graph(
            {"A": ["B"], "B": [], "island1": [], "island2": []},
            entry_node_id="A",
        )
        positions = compute_layout(graph)

        assert len(positions) == 4
        assert "island1" in positions
        assert "island2" in positions
        # Disconnected nodes are placed after the last reachable layer
        assert positions["island1"]["x"] > positions["B"]["x"]
        assert positions["island2"]["x"] > positions["B"]["x"]

    def test_entry_node_at_x_start(self):
        """Entry node is always at x=0."""
        graph = _make_graph({"start": ["mid"], "mid": ["end"], "end": []}, entry_node_id="start")
        positions = compute_layout(graph)

        assert positions["start"]["x"] == 0

    def test_positions_have_x_and_y(self):
        """Every position dict has x and y keys with float values."""
        graph = _make_graph({"A": ["B"], "B": []}, entry_node_id="A")
        positions = compute_layout(graph)

        for node_id, pos in positions.items():
            assert "x" in pos, f"Missing x for {node_id}"
            assert "y" in pos, f"Missing y for {node_id}"
            assert isinstance(pos["x"], (int, float))
            assert isinstance(pos["y"], (int, float))

    def test_single_layer_siblings_centered(self):
        """When entry fans out to 3 nodes, they are centered around y=0."""
        graph = _make_graph(
            {"root": ["a", "b", "c"], "a": [], "b": [], "c": []},
            entry_node_id="root",
        )
        positions = compute_layout(graph)

        ys = sorted([positions["a"]["y"], positions["b"]["y"], positions["c"]["y"]])
        # Centered means the middle node is at y=0
        assert ys[1] == 0
