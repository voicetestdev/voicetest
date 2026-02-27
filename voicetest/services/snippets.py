"""Snippet service: CRUD and DRY analysis for agent prompt snippets."""

from voicetest.models.agent import AgentGraph
from voicetest.services.agents import AgentService
from voicetest.snippets import suggest_snippets


class SnippetService:
    """Manages snippets and DRY analysis for agent prompts."""

    def __init__(self, agent_service: AgentService):
        self._agents = agent_service

    def get_snippets(self, agent_id: str) -> dict[str, str]:
        """Get all snippets defined for an agent."""
        _agent, graph = self._agents.load_graph(agent_id)
        return graph.snippets

    def update_all_snippets(self, agent_id: str, snippets: dict[str, str]) -> dict[str, str]:
        """Replace all snippets for an agent."""
        agent, graph = self._agents.load_graph(agent_id)
        graph.snippets = snippets
        self._agents.save_graph(agent_id, agent, graph)
        return graph.snippets

    def update_snippet(self, agent_id: str, name: str, text: str) -> dict[str, str]:
        """Create or update a single snippet."""
        agent, graph = self._agents.load_graph(agent_id)
        graph.snippets[name] = text
        self._agents.save_graph(agent_id, agent, graph)
        return graph.snippets

    def delete_snippet(self, agent_id: str, name: str) -> dict[str, str]:
        """Delete a single snippet.

        Raises:
            ValueError: If snippet not found.
        """
        agent, graph = self._agents.load_graph(agent_id)
        if name not in graph.snippets:
            raise ValueError(f"Snippet not found: {name}")
        del graph.snippets[name]
        self._agents.save_graph(agent_id, agent, graph)
        return graph.snippets

    def analyze_dry(self, agent_id: str) -> dict:
        """Run auto-DRY analysis on an agent's prompts."""
        _agent, graph = self._agents.load_graph(agent_id)
        result = suggest_snippets(graph)
        return {
            "exact": [{"text": m.text, "locations": m.locations} for m in result.exact],
            "fuzzy": [
                {"texts": m.texts, "locations": m.locations, "similarity": m.similarity}
                for m in result.fuzzy
            ],
        }

    def apply_snippets(self, agent_id: str, snippets: list[dict[str, str]]) -> AgentGraph:
        """Apply snippets: add to graph and replace occurrences in prompts with {%name%} refs."""
        agent, graph = self._agents.load_graph(agent_id)

        for snippet in snippets:
            name = snippet["name"]
            text = snippet["text"]
            graph.snippets[name] = text

            ref = "{%" + name + "%}"

            # Replace in general_prompt
            general_prompt = graph.source_metadata.get("general_prompt", "")
            if text in general_prompt:
                graph.source_metadata["general_prompt"] = general_prompt.replace(text, ref)

            # Replace in node state_prompts
            for node in graph.nodes.values():
                if text in node.state_prompt:
                    node.state_prompt = node.state_prompt.replace(text, ref)

        self._agents.save_graph(agent_id, agent, graph)
        return graph
