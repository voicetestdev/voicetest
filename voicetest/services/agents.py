"""Agent service for import/export and CRUD operations."""

import json
from pathlib import Path
from typing import Any

from voicetest.exporters.registry import ExporterRegistry
from voicetest.importers.registry import ImporterRegistry
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import MetricsConfig
from voicetest.pathutil import resolve_file
from voicetest.pathutil import resolve_path
from voicetest.storage.linked_file import check_file
from voicetest.storage.linked_file import compute_etag
from voicetest.storage.linked_file import write_json
from voicetest.storage.repositories import AgentRepository
from voicetest.templating import expand_graph_snippets
from voicetest.templating import extract_variables


class AgentService:
    """Manages agent import/export and persistence."""

    def __init__(
        self,
        agent_repo: AgentRepository,
        importer_registry: ImporterRegistry,
        exporter_registry: ExporterRegistry,
    ):
        self._repo = agent_repo
        self._importers = importer_registry
        self._exporters = exporter_registry

    async def import_agent(
        self,
        config: str | Path | dict,
        source: str | None = None,
    ) -> AgentGraph:
        """Import agent config from any supported source.

        Args:
            config: Path to config file, config dict, or string path.
            source: Source type (e.g., 'retell', 'custom'). Auto-detected if None.

        Returns:
            AgentGraph representing the agent workflow.

        Raises:
            ValueError: If source type is unknown or cannot be auto-detected.
        """
        return self._importers.import_agent(config, source_type=source)

    async def export_agent(
        self,
        graph: AgentGraph,
        format: str,
        output: Path | None = None,
        expanded: bool = False,
    ) -> str:
        """Export agent graph to specified format.

        Args:
            graph: The agent graph to export.
            format: Export format (see DiscoveryService.list_export_formats()).
            output: Optional output path. Returns string if None.
            expanded: If True, expand snippets before exporting.

        Returns:
            Exported content as string.
        """
        if expanded and graph.snippets:
            graph = expand_graph_snippets(graph)
        content = self._exporters.export(graph, format)

        if output:
            output.write_text(content)

        return content

    def list_agents(self) -> list[dict]:
        """List all agents."""
        return self._repo.list_all()

    def get_agent(self, agent_id: str) -> dict | None:
        """Get agent by ID."""
        return self._repo.get(agent_id)

    def create_agent(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        path: str | None = None,
        source: str | None = None,
    ) -> dict:
        """Create an agent from config dict or file path.

        Args:
            name: Agent display name.
            config: Agent config dict (mutually exclusive with path).
            path: Path to agent file (mutually exclusive with config).
            source: Source type override.

        Returns:
            Created agent record dict.

        Raises:
            ValueError: If neither config nor path is provided, or import fails.
            FileNotFoundError: If the path does not exist.
        """
        if not config and not path:
            raise ValueError("Either config or path is required")

        absolute_path: str | None = None
        if path:
            resolved = resolve_file(path)
            resolved.read_text()  # validates access  # nosec - path validated by resolve_file()
            absolute_path = str(resolved)

        import_source = absolute_path if absolute_path else config
        graph = self._importers.import_agent(import_source, source_type=source)

        return self._repo.create(
            name=name,
            source_type=graph.source_type,
            source_path=absolute_path,
            graph_json=graph.model_dump_json(),
        )

    def update_agent(
        self,
        agent_id: str,
        name: str | None = None,
        default_model: str | None = None,
        graph_json: str | None = None,
    ) -> dict:
        """Update an agent's name, model, or graph."""
        agent = self._repo.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        if graph_json is None and default_model is not None and agent.get("graph_json"):
            graph_data = json.loads(agent["graph_json"])
            graph_data["default_model"] = default_model if default_model else None
            graph_json = json.dumps(graph_data)

        return self._repo.update(agent_id, name=name, graph_json=graph_json)

    def delete_agent(self, agent_id: str) -> None:
        """Delete an agent by ID."""
        self._repo.delete(agent_id)

    def load_graph(self, agent_id: str) -> tuple[dict, AgentGraph]:
        """Load agent record and its graph.

        Checks source_path first (for linked-file agents) before falling back
        to the database via repo.load_graph.

        Returns:
            Tuple of (agent dict, AgentGraph).

        Raises:
            ValueError: If agent not found or graph cannot be loaded.
            FileNotFoundError: If linked file is missing.
        """
        agent = self._repo.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        source_path = agent.get("source_path")
        if source_path:
            graph = self._importers.import_agent(resolve_path(source_path))
        else:
            result = self._repo.load_graph(agent)
            graph = self._importers.import_agent(result) if isinstance(result, Path) else result

        return agent, graph

    def save_graph(self, agent_id: str, agent: dict, graph: AgentGraph) -> None:
        """Persist an updated graph back to DB or linked file.

        Raises:
            ValueError: If no exporter available for the source type.
            OSError: If linked file cannot be written.
        """
        source_path = agent.get("source_path")
        if source_path:
            self._write_graph_to_linked_file(graph, source_path, agent)
        else:
            self._repo.update(agent_id, graph_json=graph.model_dump_json())

    def get_graph_with_etag(
        self, agent_id: str, if_none_match: str | None = None
    ) -> tuple[AgentGraph | None, str | None, bool]:
        """Get agent graph with ETag support.

        Returns:
            Tuple of (graph_or_none, etag, not_modified).
            If not_modified is True, graph is None (client can use cached version).
        """
        agent = self._repo.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        source_path = agent.get("source_path")
        if source_path:
            _mtime, etag = check_file(source_path, agent_id)
            if if_none_match and if_none_match == etag:
                return None, etag, True
            graph = self._importers.import_agent(resolve_path(source_path))
            return graph, etag, False

        result = self._repo.load_graph(agent)
        graph = self._importers.import_agent(result) if isinstance(result, Path) else result

        updated_at = agent.get("updated_at", "")
        etag = compute_etag(agent_id, updated_at)
        if if_none_match and if_none_match == etag:
            return None, etag, True

        return graph, etag, False

    def get_variables(self, agent_id: str) -> list[str]:
        """Extract dynamic variable names from agent prompts.

        Scans general_prompt and all node state_prompt values for {{var}} placeholders.
        Returns unique variable names in first-appearance order.
        """
        _agent, graph = self.load_graph(agent_id)

        texts = []
        general_prompt = graph.source_metadata.get("general_prompt", "")
        if general_prompt:
            texts.append(general_prompt)
        for node in graph.nodes.values():
            if node.state_prompt:
                texts.append(node.state_prompt)

        combined = "\n".join(texts)
        return extract_variables(combined)

    def update_prompt(
        self,
        agent_id: str,
        prompt_text: str,
        node_id: str | None = None,
        transition_target_id: str | None = None,
    ) -> AgentGraph:
        """Update a general or node-specific prompt.

        When node_id is None, updates source_metadata.general_prompt.
        When node_id is set and transition_target_id is None, updates that node's state_prompt.
        When both are set, updates transition condition value.

        Returns:
            Updated AgentGraph.
        """
        agent, graph = self.load_graph(agent_id)

        if node_id is None:
            graph.source_metadata["general_prompt"] = prompt_text
        elif transition_target_id is not None:
            node = graph.get_node(node_id)
            if not node:
                raise ValueError(f"Node not found: {node_id}")
            transition = next(
                (t for t in node.transitions if t.target_node_id == transition_target_id),
                None,
            )
            if not transition:
                raise ValueError(f"Transition not found: {node_id} -> {transition_target_id}")
            transition.condition.value = prompt_text
        else:
            node = graph.get_node(node_id)
            if not node:
                raise ValueError(f"Node not found: {node_id}")
            node.state_prompt = prompt_text

        self.save_graph(agent_id, agent, graph)
        return graph

    def update_metadata(self, agent_id: str, updates: dict[str, Any]) -> AgentGraph:
        """Merge updates into an agent's source_metadata."""
        agent, graph = self.load_graph(agent_id)
        graph.source_metadata.update(updates)
        self.save_graph(agent_id, agent, graph)
        return graph

    def get_metrics_config(self, agent_id: str) -> MetricsConfig:
        """Get an agent's metrics configuration."""
        return self._repo.get_metrics_config(agent_id)

    def update_metrics_config(self, agent_id: str, config: MetricsConfig) -> MetricsConfig:
        """Update an agent's metrics configuration."""
        self._repo.update_metrics_config(agent_id, config)
        return config

    def _write_graph_to_linked_file(self, graph: AgentGraph, source_path: str, agent: dict) -> None:
        """Export a graph back to a linked file on disk."""
        source_type = agent.get("source_type", "")

        # Try format-based exporter (e.g. retell-llm)
        exporter = self._exporters.get(source_type)
        if exporter:
            exported = json.loads(exporter.export(graph))
            try:
                write_json(source_path, exported)
            except PermissionError:
                raise ValueError(f"Cannot write to linked file: {source_path}") from None
            return

        raise ValueError(f"No exporter available for source type: {source_type}")
