"""BFS-based layout algorithm for agent graph visualization."""

from collections import deque

from voicetest.models.agent import AgentGraph


X_SPACING = 500
Y_SPACING = 250
X_START = 0


def compute_layout(graph: AgentGraph) -> dict[str, dict[str, float]]:
    """Compute display positions for all nodes in the graph.

    Uses BFS from the entry node to assign each node a layer (depth).
    Nodes in the same layer are spread vertically, centered on y=0.
    Unreachable nodes are appended to the last layer + 1.

    Returns:
        Mapping of node_id to {"x": float, "y": float}.
    """
    layers: dict[int, list[str]] = {}
    visited: dict[str, int] = {}

    # BFS from entry node
    queue: deque[tuple[str, int]] = deque()
    queue.append((graph.entry_node_id, 0))
    visited[graph.entry_node_id] = 0

    while queue:
        node_id, depth = queue.popleft()
        layers.setdefault(depth, []).append(node_id)

        node = graph.nodes.get(node_id)
        if not node:
            continue

        for transition in node.transitions:
            target = transition.target_node_id
            if target not in visited and target in graph.nodes:
                visited[target] = depth + 1
                queue.append((target, depth + 1))

    # Place unreachable nodes in an extra layer
    max_layer = max(layers.keys()) if layers else 0
    unreachable = [nid for nid in graph.nodes if nid not in visited]
    if unreachable:
        layers[max_layer + 1] = unreachable

    # Convert layers to positions
    positions: dict[str, dict[str, float]] = {}
    for depth, node_ids in layers.items():
        x = X_START + depth * X_SPACING
        count = len(node_ids)
        for i, node_id in enumerate(node_ids):
            y = (i - (count - 1) / 2) * Y_SPACING
            positions[node_id] = {"x": float(x), "y": float(y)}

    return positions
