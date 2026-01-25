"""LiveKit platform client management.

Handles credential loading and agent deployment via CLI.
LiveKit agents are Python code deployed via the `lk` CLI tool.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


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
            from voicetest.exporters.livekit_codegen import export_livekit_code
            from voicetest.models.agent import AgentGraph

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
