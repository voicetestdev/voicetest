"""Graph visualization exporters."""

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph


def _escape_mermaid_text(text: str) -> str:
    """Escape special characters for Mermaid labels."""
    return (
        text.replace('"', "'").replace("\n", " ").replace("{", "#lbrace;").replace("}", "#rbrace;")
    )


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

    # Add nodes with truncated state prompts
    for node_id, node in graph.nodes.items():
        escaped_node_id = _escape_mermaid_text(node_id)

        if node.is_extract_node():
            # Extract nodes get a hexagon shape with their name and variable list
            name = node.metadata.get("name", node_id)
            name = _escape_mermaid_text(str(name))
            var_names = ", ".join(v.name for v in node.variables_to_extract)
            var_names = _escape_mermaid_text(var_names)
            lines.append(f'    {node_id}{{{{"Extract<br/>{name}<br/>[{var_names}]"}}}}')
        elif node.is_logic_node():
            # Logic split nodes get a diamond shape with their name
            name = node.metadata.get("name", node_id)
            name = _escape_mermaid_text(str(name))
            lines.append(f'    {node_id}{{"Logic Split<br/>{name}"}}')
        else:
            # Truncate long state prompts
            label = node.state_prompt[:50]
            if len(node.state_prompt) > 50:
                label += "..."
            label = _escape_mermaid_text(label)
            lines.append(f'    {node_id}["{escaped_node_id}<br/>{label}"]')

        # Check for end_call tool
        if node.tools:
            for tool in node.tools:
                if tool.name == "end_call" or getattr(tool, "type", "") == "end_call":
                    desc = tool.description[:30] if tool.description else "End call"
                    if len(tool.description) > 30:
                        desc += "..."
                    desc = _escape_mermaid_text(desc)
                    nodes_with_end_call.append((node_id, desc))
                    break

    # Add edges
    for node_id, node in graph.nodes.items():
        for transition in node.transitions:
            condition_text = transition.condition.value.strip()
            if condition_text:
                condition_label = condition_text[:30]
                if len(condition_text) > 30:
                    condition_label += "..."
                condition_label = _escape_mermaid_text(condition_label)
                lines.append(f'    {node_id} -->|"{condition_label}"| {transition.target_node_id}')
            else:
                lines.append(f"    {node_id} --> {transition.target_node_id}")

    # Add end_call node and edges if any nodes have end_call tool
    if nodes_with_end_call:
        lines.append('    end_call(("End Call"))')
        for node_id, description in nodes_with_end_call:
            lines.append(f'    {node_id} -->|"{description}"| end_call')
        lines.append("    style end_call fill:#dc2626,color:#ffffff")

    # Style global nodes with a purple border
    for global_node in graph.global_nodes:
        lines.append(f"    style {global_node.id} stroke:#7c3aed,stroke-width:3px")

    # Mark entry node with green fill and contrasting text
    lines.append(f"    style {graph.entry_node_id} fill:#16a34a,color:#ffffff")

    return "\n".join(lines)
