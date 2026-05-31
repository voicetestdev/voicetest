"""Agent service for import/export and CRUD operations."""

import json
from pathlib import Path
from typing import Any

from voicetest.exporters.registry import ExporterRegistry
from voicetest.importers.registry import ImporterRegistry
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import GlobalNodeSetting
from voicetest.models.agent import GoBackCondition
from voicetest.models.agent import MetricsConfig
from voicetest.models.agent import TransitionCondition
from voicetest.storage.linked_file import check_file
from voicetest.storage.linked_file import compute_etag
from voicetest.storage.linked_file import write_json
from voicetest.storage.repositories import AgentRepository
from voicetest.util.pathutil import resolve_file
from voicetest.util.pathutil import resolve_path
from voicetest.util.templating import expand_graph_snippets
from voicetest.util.templating import extract_variables


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
        """Import agent config from any supported source."""
        return self._importers.import_agent(config, source_type=source)

    async def export_agent(
        self,
        graph: AgentGraph,
        format: str,
        output: Path | None = None,
        expanded: bool = False,
    ) -> str:
        """Export agent graph to specified format."""
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
        """Create an agent from config dict or file path."""
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

        if graph_json is None and default_model is not None:
            stored = self._repo.get_graph_json(agent_id)
            if stored:
                graph_data = json.loads(stored)
                graph_data["default_model"] = default_model if default_model else None
                graph_json = json.dumps(graph_data)

        return self._repo.update(agent_id, name=name, graph_json=graph_json)

    def delete_agent(self, agent_id: str) -> None:
        """Delete an agent by ID."""
        self._repo.delete(agent_id)

    def migrate_node_types(self) -> dict:
        """Backfill `node_type` on stored graphs that predate the required field."""
        return self._repo.migrate_node_types()

    def load_graph(self, agent_id: str) -> tuple[dict, AgentGraph]:
        """Load agent record and its graph (linked file first, else DB)."""
        agent = self._repo.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        return agent, self._load_graph_payload(agent, agent_id)

    def save_graph(self, agent_id: str, agent: dict, graph: AgentGraph) -> None:
        """Persist an updated graph back to DB or linked file."""
        source_path = agent.get("source_path")
        if source_path:
            self._write_graph_to_linked_file(graph, source_path, agent)
        else:
            self._repo.update(agent_id, graph_json=graph.model_dump_json())

    def get_graph_with_etag(
        self, agent_id: str, if_none_match: str | None = None
    ) -> tuple[AgentGraph | None, str | None, bool]:
        """Get agent graph with ETag support.

        Returns (graph_or_none, etag, not_modified). When not_modified is True,
        graph is None so the client can use its cached version."""
        agent = self._repo.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        source_path = agent.get("source_path")
        if source_path:
            _mtime, etag = check_file(source_path, agent_id)
        else:
            etag = compute_etag(agent_id, agent.get("updated_at", ""))

        if if_none_match and if_none_match == etag:
            return None, etag, True

        return self._load_graph_payload(agent, agent_id), etag, False

    def _load_graph_payload(self, agent: dict, agent_id: str) -> AgentGraph:
        """Resolve the graph for an agent: re-import the linked file if any, else DB."""
        source_path = agent.get("source_path")
        if source_path:
            return self._importers.import_agent(resolve_path(source_path))
        result = self._repo.load_graph(agent_id)
        return self._importers.import_agent(result) if isinstance(result, Path) else result

    def get_variables(self, agent_id: str) -> list[str]:
        """Extract dynamic variable names from agent prompts."""
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
        When both are set, updates transition condition value."""
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

    def update_global_node_setting(
        self,
        agent_id: str,
        node_id: str,
        setting: dict[str, Any] | None,
    ) -> AgentGraph:
        """Set or remove a node's global_node_setting."""
        agent, graph = self.load_graph(agent_id)
        node = graph.get_node(node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        if setting is None:
            node.global_node_setting = None
        else:
            go_backs = [
                GoBackCondition(
                    id=gb["id"],
                    condition=TransitionCondition(
                        type="llm_prompt",
                        value=gb["condition"],
                    ),
                )
                for gb in setting.get("go_back_conditions", [])
            ]
            node.global_node_setting = GlobalNodeSetting(
                condition=setting["condition"],
                go_back_conditions=go_backs,
            )

        self.save_graph(agent_id, agent, graph)
        return graph

    def get_metrics_config(self, agent_id: str) -> MetricsConfig:
        """Get an agent's metrics configuration."""
        return self._repo.get_metrics_config(agent_id)

    def update_metrics_config(self, agent_id: str, config: MetricsConfig) -> MetricsConfig:
        """Update an agent's metrics configuration."""
        self._repo.update_metrics_config(agent_id, config)
        return config

    # Importer source_type to exporter format_id mapping when they differ
    _SOURCE_TYPE_TO_FORMAT: dict[str, str] = {
        "retell": "retell-cf",
    }

    def _write_graph_to_linked_file(self, graph: AgentGraph, source_path: str, agent: dict) -> None:
        """Export a graph back to a linked file on disk."""
        source_type = agent.get("source_type", "")
        format_id = self._SOURCE_TYPE_TO_FORMAT.get(source_type, source_type)

        exporter = self._exporters.get(format_id)
        if exporter:
            exported = json.loads(exporter.export(graph))
            try:
                write_json(source_path, exported)
            except PermissionError:
                raise ValueError(f"Cannot write to linked file: {source_path}") from None
            return

        raise ValueError(f"No exporter available for source type: {source_type}")
