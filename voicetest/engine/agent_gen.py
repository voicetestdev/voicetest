"""Agent class generation from AgentGraph.

This module converts the unified AgentGraph representation into
LiveKit Agent classes that can be executed.
"""

from collections.abc import Callable
from typing import Any

from voicetest.models.agent import AgentGraph, AgentNode, Transition


class GeneratedAgent:
    """Base class for dynamically generated agents.

    This provides a simpler interface than LiveKit's actual Agent class
    for testing purposes, while maintaining compatibility with the
    LiveKit execution model.
    """

    _node_id: str = ""

    def __init__(self, instructions: str = ""):
        self.instructions = instructions
        self._transition_tools: list[Callable] = []

    def add_transition_tool(self, tool: Callable) -> None:
        """Register a transition tool."""
        self._transition_tools.append(tool)


def generate_agent_classes(graph: AgentGraph) -> dict[str, type[GeneratedAgent]]:
    """Generate agent classes from AgentGraph.

    Each node in the graph becomes a separate agent class with:
    - Instructions from the node
    - Transition tools for each outgoing edge

    Args:
        graph: The agent graph to convert.

    Returns:
        Dictionary mapping node IDs to generated agent classes.
    """
    agent_classes: dict[str, type[GeneratedAgent]] = {}

    for node_id, node in graph.nodes.items():
        agent_class = _create_agent_class(node, graph)
        agent_classes[node_id] = agent_class

    return agent_classes


def _create_agent_class(node: AgentNode, graph: AgentGraph) -> type[GeneratedAgent]:
    """Create a single agent class for a node."""

    # Capture node values for closure
    node_instructions = node.instructions
    node_id = node.id
    transitions = node.transitions

    class NodeAgent(GeneratedAgent):
        _node_id = node_id

        def __init__(self):
            super().__init__(instructions=node_instructions)
            # Create and register transition tools
            for transition in transitions:
                tool = _create_transition_tool(transition, graph)
                self.add_transition_tool(tool)

    # Set class name for debugging
    NodeAgent.__name__ = f"Agent_{node_id}"
    NodeAgent.__qualname__ = f"Agent_{node_id}"

    return NodeAgent


def _create_transition_tool(
    transition: Transition,
    graph: AgentGraph,
) -> Callable[..., Any]:
    """Create a transition tool function.

    The tool's docstring is set to the transition condition,
    which the LLM uses to decide when to call it.
    """
    target_id = transition.target_node_id
    condition_value = transition.condition.value

    async def transition_tool(**kwargs: Any) -> tuple[str, str]:
        """Transition to target node."""
        return target_id, ""

    # Set docstring to condition (LLM uses this)
    transition_tool.__doc__ = condition_value
    transition_tool.__name__ = f"route_to_{target_id}"

    return transition_tool
