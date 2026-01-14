"""Graph visualization exporters."""

from voicetest.models.agent import AgentGraph


def export_mermaid(graph: AgentGraph) -> str:
    """Export AgentGraph to Mermaid flowchart format.

    Args:
        graph: The agent graph to export.

    Returns:
        Mermaid flowchart definition string.
    """
    lines = ["flowchart TD"]

    # Add nodes
    for node_id, node in graph.nodes.items():
        # Truncate long instructions
        label = node.instructions[:50]
        if len(node.instructions) > 50:
            label += "..."
        # Escape quotes for Mermaid
        label = label.replace('"', "'").replace("\n", " ")
        lines.append(f'    {node_id}["{node_id}<br/>{label}"]')

    # Add edges
    for node_id, node in graph.nodes.items():
        for transition in node.transitions:
            # Truncate long conditions
            condition_label = transition.condition.value[:30]
            if len(transition.condition.value) > 30:
                condition_label += "..."
            condition_label = condition_label.replace('"', "'").replace("\n", " ")
            lines.append(
                f'    {node_id} -->|"{condition_label}"| {transition.target_node_id}'
            )

    # Mark entry node with green fill
    lines.append(f"    style {graph.entry_node_id} fill:#90EE90")

    return "\n".join(lines)
