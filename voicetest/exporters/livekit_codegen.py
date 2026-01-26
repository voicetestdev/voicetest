"""LiveKit code generation exporter."""

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph, AgentNode


class LiveKitExporter:
    """Exports AgentGraph to LiveKit Python agent code."""

    format_id = "livekit"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="LiveKit",
            description="Python agent code for LiveKit voice platform",
            ext="py",
        )

    def export(self, graph: AgentGraph) -> str:
        return export_livekit_code(graph)


def export_livekit_code(graph: AgentGraph) -> str:
    """Generate Python code for LiveKit agents from AgentGraph.

    Args:
        graph: The agent graph to export.

    Returns:
        Python source code string.
    """
    lines = [
        '"""Generated LiveKit agents from voicetest."""',
        "",
        "from livekit.agents import Agent, RunContext, function_tool",
        "",
    ]

    # Generate agent classes
    for _node_id, node in graph.nodes.items():
        lines.extend(_generate_agent_class(node, graph))
        lines.append("")

    # Generate entry point
    lines.extend(
        [
            "",
            f"# Entry point: {graph.entry_node_id}",
            "def get_entry_agent():",
            f"    return Agent_{graph.entry_node_id}()",
        ]
    )

    return "\n".join(lines)


def _generate_agent_class(node: AgentNode, graph: AgentGraph) -> list[str]:
    """Generate code for a single agent class."""
    # Escape the instructions for use in a triple-quoted string
    instructions = node.instructions.replace('"""', '\\"\\"\\"')

    lines = [
        f"class Agent_{node.id}(Agent):",
        f'    """Agent for node: {node.id}"""',
        "",
        "    def __init__(self):",
        "        super().__init__(",
        f'            instructions="""{instructions}"""',
        "        )",
    ]

    # Generate transition tools
    for transition in node.transitions:
        condition = transition.condition.value.replace('"""', '\\"\\"\\"')
        lines.extend(
            [
                "",
                "    @function_tool",
                f"    async def route_to_{transition.target_node_id}(self, ctx: RunContext):",
                f'        """{condition}"""',
                f"        return Agent_{transition.target_node_id}(), ''",
            ]
        )

    return lines
