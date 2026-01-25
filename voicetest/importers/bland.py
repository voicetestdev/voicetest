"""Bland AI inbound number configuration importer."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    ToolDefinition,
)


class BlandTool(BaseModel):
    """Bland AI custom tool definition."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = Field(default=None, alias="input_schema")
    speech: str = ""
    api: dict[str, Any] | None = None


class BlandInboundConfig(BaseModel):
    """Bland AI inbound number configuration."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    phone_number: str | None = Field(default=None, alias="phone_number")
    prompt: str = ""
    voice_id: int | None = Field(default=None, alias="voice_id")
    webhook: str | None = None
    first_sentence: str | None = Field(default=None, alias="first_sentence")
    record: bool | None = None
    max_duration: int | None = Field(default=None, alias="max_duration")
    transfer_phone_number: str | None = Field(default=None, alias="transfer_phone_number")
    transfer_list: dict[str, str] | None = Field(default=None, alias="transfer_list")
    model: str | None = None
    tools: list[BlandTool] | None = Field(default=None)
    dynamic_data: str | None = Field(default=None, alias="dynamic_data")
    interruption_threshold: int | None = Field(default=None, alias="interruption_threshold")


class BlandImporter:
    """Import Bland AI inbound number configurations."""

    @property
    def source_type(self) -> str:
        return "bland"

    def get_info(self) -> ImporterInfo:
        return ImporterInfo(
            source_type="bland",
            description="Import Bland AI inbound number configurations",
            file_patterns=["*.json"],
        )

    def can_import(self, path_or_config: str | Path | dict) -> bool:
        """Detect Bland format by checking for characteristic fields."""
        try:
            config = self._load_config(path_or_config)
            return self._is_bland_config(config)
        except Exception:
            return False

    def _is_bland_config(self, config: dict) -> bool:
        """Check if config is a Bland AI inbound number configuration."""
        # Bland configs have prompt and often phone_number
        has_prompt = "prompt" in config
        has_phone = "phone_number" in config

        # Check for Bland-specific fields
        has_bland_fields = any(
            key in config
            for key in [
                "first_sentence",
                "voice_id",
                "transfer_list",
                "interruption_threshold",
                "max_duration",
                "dynamic_data",
            ]
        )

        # Distinguish from other formats
        is_not_vapi = "model" not in config or not isinstance(config.get("model"), dict)
        is_not_retell_llm = "general_prompt" not in config and "llm_id" not in config
        is_not_retell_cf = "start_node_id" not in config and "nodes" not in config
        is_not_livekit = "from livekit" not in str(config.get("code", ""))

        return (
            has_prompt
            and (has_phone or has_bland_fields)
            and is_not_vapi
            and is_not_retell_llm
            and is_not_retell_cf
            and is_not_livekit
        )

    def import_agent(self, path_or_config: str | Path | dict) -> AgentGraph:
        """Convert Bland AI inbound config to AgentGraph."""
        raw_config = self._load_config(path_or_config)
        config = BlandInboundConfig.model_validate(raw_config)

        # Convert tools
        tools = self._convert_tools(config.tools or [])

        # Create single node (Bland doesn't have multi-agent flows)
        node_id = "main"
        nodes = {
            node_id: AgentNode(
                id=node_id,
                instructions=config.prompt,
                tools=tools,
                transitions=[],
                metadata={"first_sentence": config.first_sentence} if config.first_sentence else {},
            )
        }

        # Build source metadata
        source_metadata = self._build_metadata(config)

        return AgentGraph(
            nodes=nodes,
            entry_node_id=node_id,
            source_type="bland",
            source_metadata=source_metadata,
        )

    def _convert_tools(self, tools: list[BlandTool]) -> list[ToolDefinition]:
        """Convert Bland tools to ToolDefinition."""
        result = []
        for tool in tools:
            result.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.input_schema or {},
                )
            )
        return result

    def _build_metadata(self, config: BlandInboundConfig) -> dict[str, Any]:
        """Build source metadata from Bland config."""
        metadata: dict[str, Any] = {}

        if config.phone_number:
            metadata["phone_number"] = config.phone_number
        if config.voice_id is not None:
            metadata["voice_id"] = config.voice_id
        if config.webhook:
            metadata["webhook"] = config.webhook
        if config.first_sentence:
            metadata["first_sentence"] = config.first_sentence
        if config.record is not None:
            metadata["record"] = config.record
        if config.max_duration is not None:
            metadata["max_duration"] = config.max_duration
        if config.transfer_phone_number:
            metadata["transfer_phone_number"] = config.transfer_phone_number
        if config.transfer_list:
            metadata["transfer_list"] = config.transfer_list
        if config.model:
            metadata["model"] = config.model
        if config.interruption_threshold is not None:
            metadata["interruption_threshold"] = config.interruption_threshold

        return metadata

    def _load_config(self, path_or_config: str | Path | dict) -> dict[str, Any]:
        """Load config from path or return dict directly."""
        if isinstance(path_or_config, dict):
            return path_or_config
        path = Path(path_or_config)
        return json.loads(path.read_text())
