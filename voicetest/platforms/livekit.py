"""LiveKit platform client management.

Handles credential loading and agent deployment via CLI.
LiveKit agents are Python code deployed via the `lk` CLI tool.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import TYPE_CHECKING
from typing import Any

from voicetest.exporters.livekit_codegen import export_livekit_code
from voicetest.importers.livekit import LiveKitImporter
from voicetest.models.agent import AgentGraph


if TYPE_CHECKING:
    from voicetest.platforms.base import SourceImporter


class LiveKitPlatformClient:
    """LiveKit platform client implementing PlatformClient protocol.

    Unlike Retell/VAPI, LiveKit agents are Python code deployed via CLI,
    not JSON configs uploaded via HTTP API.
    """

    @property
    def platform_name(self) -> str:
        """Platform identifier."""
        return "livekit"

    @property
    def env_key(self) -> str:
        """Environment variable name for API key."""
        return "LIVEKIT_API_KEY"

    @property
    def required_env_keys(self) -> list[str]:
        """All environment variable names required for this platform."""
        return ["LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]

    def get_importer(self) -> SourceImporter:
        """Get the importer for this platform."""
        return LiveKitImporter()

    def get_exporter(self) -> Callable[[AgentGraph], dict[str, Any]]:
        """Get the exporter function for this platform."""

        def _export_with_code(graph: AgentGraph) -> dict[str, Any]:
            return {"code": export_livekit_code(graph), "graph": graph}

        return _export_with_code

    def get_client(self, api_key: str | None = None) -> dict[str, str]:
        """Get LiveKit credentials as a dict (no SDK client).

        LiveKit uses the `lk` CLI tool rather than an SDK client.
        This returns credentials needed for CLI operations.

        Args:
            api_key: LiveKit API key. Defaults to LIVEKIT_API_KEY env var.

        Returns:
            Dict with api_key, api_secret, and url.

        Raises:
            ValueError: If credentials are not available.
        """
        key = api_key or os.environ.get(self.env_key)
        secret = os.environ.get("LIVEKIT_API_SECRET")
        url = os.environ.get("LIVEKIT_URL", "wss://cloud.livekit.io")

        if not key or not secret:
            raise ValueError(f"{self.env_key} and LIVEKIT_API_SECRET must be set")

        return {
            "api_key": key,
            "api_secret": secret,
            "url": url,
        }

    def _run_lk_command(
        self, args: list[str], credentials: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess:
        """Run a `lk` CLI command.

        Args:
            args: Command arguments (without 'lk' prefix).
            credentials: Optional credentials dict from get_client().

        Returns:
            Completed process result.
        """
        env = os.environ.copy()
        if credentials:
            env["LIVEKIT_API_KEY"] = credentials["api_key"]
            env["LIVEKIT_API_SECRET"] = credentials["api_secret"]
            env["LIVEKIT_URL"] = credentials["url"]

        return subprocess.run(
            ["lk", *args],
            capture_output=True,
            text=True,
            env=env,
        )

    def list_agents(self, client: dict[str, str]) -> list[dict[str, Any]]:
        """List agents from LiveKit Cloud via CLI.

        Args:
            client: Credentials dict from get_client().

        Returns:
            List of dicts with id and name fields.
        """
        result = self._run_lk_command(["agent", "list", "--json"], client)
        if result.returncode != 0:
            return []

        try:
            agents = json.loads(result.stdout)
            return [
                {"id": a.get("id", a.get("name", "")), "name": a.get("name", a.get("id", ""))}
                for a in agents
            ]
        except json.JSONDecodeError:
            return []

    def get_agent(self, client: dict[str, str], agent_id: str) -> dict[str, Any]:
        """Get agent info by ID.

        Args:
            client: Credentials dict from get_client().
            agent_id: Agent identifier.

        Returns:
            Agent info dict.
        """
        result = self._run_lk_command(["agent", "info", agent_id, "--json"], client)
        if result.returncode != 0:
            raise ValueError(f"Failed to get agent {agent_id}: {result.stderr}")

        return json.loads(result.stdout)

    def create_agent(
        self, client: dict[str, str], config: dict[str, Any], name: str | None = None
    ) -> dict[str, Any]:
        """Create/deploy an agent to LiveKit Cloud.

        This generates a Python agent file and deploys it via CLI.

        Args:
            client: Credentials dict from get_client().
            config: Dict containing 'code' (Python source) or AgentGraph.
            name: Optional agent name.

        Returns:
            Dict with id, name, platform, and code_path fields.
        """
        code = config.get("code")
        if not code:
            graph_data = config.get("graph")
            if graph_data:
                if isinstance(graph_data, dict):
                    graph = AgentGraph.model_validate(graph_data)
                else:
                    graph = graph_data
                code = export_livekit_code(graph)
            else:
                raise ValueError("config must contain 'code' or 'graph'")

        agent_name = name or "voicetest-agent"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix=f"{agent_name}_"
        ) as f:
            f.write(code)
            code_path = f.name

        try:
            result = self._run_lk_command(
                ["agent", "deploy", code_path, "--name", agent_name],
                client,
            )
            if result.returncode != 0:
                raise ValueError(f"Failed to deploy agent: {result.stderr}")

            try:
                deploy_result = json.loads(result.stdout)
                agent_id = deploy_result.get("id", agent_name)
            except json.JSONDecodeError:
                agent_id = agent_name

            return {
                "id": agent_id,
                "name": agent_name,
                "platform": self.platform_name,
                "code_path": code_path,
            }
        except Exception:
            Path(code_path).unlink(missing_ok=True)
            raise

    def delete_agent(self, client: dict[str, str], agent_id: str) -> None:
        """Delete an agent from LiveKit Cloud.

        Args:
            client: Credentials dict from get_client().
            agent_id: Agent identifier.
        """
        result = self._run_lk_command(["agent", "delete", agent_id], client)
        if result.returncode != 0:
            raise ValueError(f"Failed to delete agent {agent_id}: {result.stderr}")

    @property
    def supports_update(self) -> bool:
        """LiveKit supports updating agents (deploy is upsert)."""
        return True

    @property
    def remote_id_key(self) -> str:
        """Key in source_metadata for LiveKit agent ID."""
        return "agent_id"

    def update_agent(
        self, client: dict[str, str], agent_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing agent in LiveKit Cloud.

        LiveKit deploy is an upsert operation, so we use create_agent
        with the same name to update.

        Args:
            client: Credentials dict from get_client().
            agent_id: Agent identifier (used as name).
            config: Dict containing 'code' or 'graph'.

        Returns:
            Dict with id, name, platform, and code_path fields.
        """
        return self.create_agent(client, config, name=agent_id)


def get_client(api_key: str | None = None) -> dict[str, str]:
    """Get LiveKit credentials.

    Args:
        api_key: LiveKit API key. Defaults to LIVEKIT_API_KEY env var.

    Returns:
        Dict with api_key, api_secret, and url.

    Raises:
        ValueError: If credentials are not available.
    """
    return LiveKitPlatformClient().get_client(api_key)
