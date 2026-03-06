"""LiveKit code generation exporter."""

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode


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
    # Build map of logic node IDs to their transitions so predecessors
    # can generate deterministic routing code instead of function tools.
    logic_nodes = {nid: node for nid, node in graph.nodes.items() if node.is_logic_node()}

    lines = [
        '"""Generated LiveKit agents from voicetest."""',
        "",
        "from livekit.agents import Agent, RunContext, function_tool",
        "",
    ]

    # Generate agent classes, skipping logic split nodes
    for _node_id, node in graph.nodes.items():
        if node.is_logic_node():
            continue
        lines.extend(_generate_agent_class(node, graph, logic_nodes))
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


def _generate_agent_class(
    node: AgentNode,
    graph: AgentGraph,
    logic_nodes: dict[str, AgentNode] | None = None,
) -> list[str]:
    """Generate code for a single agent class."""
    logic_nodes = logic_nodes or {}

    # Only add general_prompt to entry node
    is_entry = node.id == graph.entry_node_id
    general_prompt = graph.source_metadata.get("general_prompt", "") if is_entry else ""

    if general_prompt and node.state_prompt:
        full_instructions = f"{general_prompt}\n\n{node.state_prompt}"
    else:
        full_instructions = node.state_prompt or general_prompt

    # Escape for triple-quoted string
    instructions = full_instructions.replace('"""', '\\"\\"\\"')

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
        target_id = transition.target_node_id
        if target_id in logic_nodes:
            # Logic node: generate deterministic routing method
            lines.extend(_generate_logic_routing(target_id, logic_nodes[target_id]))
        else:
            condition = transition.condition.value.replace('"""', '\\"\\"\\"')
            lines.extend(
                [
                    "",
                    "    @function_tool",
                    f"    async def route_to_{target_id}(self, ctx: RunContext):",
                    f'        """{condition}"""',
                    f"        return Agent_{target_id}(), ''",
                ]
            )

    return lines


def _generate_logic_routing(
    logic_node_id: str,
    logic_node: AgentNode,
) -> list[str]:
    """Generate deterministic if/elif/else routing for a logic split node."""
    lines = [
        "",
        f"    # Deterministic routing via logic split: {logic_node_id}",
        "    @function_tool",
        f"    async def route_via_{logic_node_id}(self, ctx: RunContext):",
        '        """Deterministic routing based on variable conditions."""',
        "        variables = ctx.get('dynamic_variables', {})",
    ]

    first = True
    for transition in logic_node.transitions:
        target_id = transition.target_node_id
        if transition.condition.type == "always":
            lines.append("        else:")
            lines.append(f"            return Agent_{target_id}(), ''")
        elif transition.condition.type == "equation":
            keyword = "if" if first else "elif"
            # Build condition expression from equations
            condition_expr = _equation_to_python(transition)
            lines.append(f"        {keyword} {condition_expr}:")
            lines.append(f"            return Agent_{target_id}(), ''")
            first = False

    return lines


def _equation_to_python(transition) -> str:
    """Convert equation transition to a Python condition expression."""
    if transition.condition.equations:
        parts = []
        for eq in transition.condition.equations:
            parts.append(f"variables.get('{eq.left}') {eq.operator} '{eq.right}'")
        return " and ".join(parts)
    # Fallback to the value string
    return f"# {transition.condition.value}"
