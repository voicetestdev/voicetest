"""Graph visualization exporters."""

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph


class MermaidExporter:
    """Exports AgentGraph to Mermaid flowchart format."""

    format_id = "mermaid"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="Mermaid",
            description="Flowchart diagram for documentation and visualization",
            ext="md",
        )

    def export(self, graph: AgentGraph) -> str:
        return export_mermaid(graph)


def export_mermaid(graph: AgentGraph) -> str:
    """Export AgentGraph to Mermaid flowchart format.

    Args:
        graph: The agent graph to export.

    Returns:
        Mermaid flowchart definition string.
    """
    lines = ["flowchart TD"]

    # Track nodes with end_call tool
    nodes_with_end_call: list[tuple[str, str]] = []

    # Add nodes
    for node_id, node in graph.nodes.items():
        # Truncate long instructions
        label = node.instructions[:50]
        if len(node.instructions) > 50:
            label += "..."
        # Escape quotes for Mermaid
        label = label.replace('"', "'").replace("\n", " ")
        lines.append(f'    {node_id}["{node_id}<br/>{label}"]')

        # Check for end_call tool
        if node.tools:
            for tool in node.tools:
                if tool.name == "end_call" or getattr(tool, "type", "") == "end_call":
                    desc = tool.description[:30] if tool.description else "End call"
                    if len(tool.description) > 30:
                        desc += "..."
                    desc = desc.replace('"', "'").replace("\n", " ")
                    nodes_with_end_call.append((node_id, desc))
                    break

    # Add edges
    for node_id, node in graph.nodes.items():
        for transition in node.transitions:
            # Truncate long conditions
            condition_label = transition.condition.value[:30]
            if len(transition.condition.value) > 30:
                condition_label += "..."
            condition_label = condition_label.replace('"', "'").replace("\n", " ")
            lines.append(f'    {node_id} -->|"{condition_label}"| {transition.target_node_id}')

    # Add end_call node and edges if any nodes have end_call tool
    if nodes_with_end_call:
        lines.append('    end_call(("End Call"))')
        for node_id, description in nodes_with_end_call:
            lines.append(f'    {node_id} -->|"{description}"| end_call')
        lines.append("    style end_call fill:#dc2626,color:#ffffff")

    # Mark entry node with green fill and contrasting text
    lines.append(f"    style {graph.entry_node_id} fill:#16a34a,color:#ffffff")

    return "\n".join(lines)
