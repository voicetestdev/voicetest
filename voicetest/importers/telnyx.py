"""Telnyx AI assistant configuration importer."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


class TelnyxHandoffTarget(BaseModel):
    """A single handoff target referencing another AI assistant."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class TelnyxHandoff(BaseModel):
    """Handoff tool configuration for multi-agent routing."""

    model_config = ConfigDict(extra="ignore")

    ai_assistants: list[TelnyxHandoffTarget] = Field(default_factory=list)
    voice_mode: str | None = None


class TelnyxWebhook(BaseModel):
    """Webhook tool configuration."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    url: str | None = None
    method: str | None = None
    path_parameters: dict[str, Any] | None = None
    query_parameters: dict[str, Any] | None = None
    body_parameters: dict[str, Any] | None = None
    headers: list[dict[str, Any]] | None = None
    timeout_ms: int | None = None


class TelnyxTransfer(BaseModel):
    """Transfer tool configuration."""

    model_config = ConfigDict(extra="ignore")

    targets: list[dict[str, Any]] = Field(default_factory=list)
    from_: str | None = Field(default=None, alias="from")


class TelnyxTool(BaseModel):
    """A single tool in the Telnyx assistant config."""

    model_config = ConfigDict(extra="ignore")

    type: str
    webhook: TelnyxWebhook | None = None
    handoff: TelnyxHandoff | None = None
    transfer: TelnyxTransfer | None = None
    hangup: dict[str, Any] | None = None


class TelnyxAssistantConfig(BaseModel):
    """Telnyx AI assistant configuration."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = None
    name: str | None = None
    instructions: str = ""
    model: str | None = None
    greeting: str | None = None
    voice_settings: dict[str, Any] | None = None
    transcription: dict[str, Any] | None = None
    telephony_settings: dict[str, Any] | None = None
    dynamic_variables: dict[str, Any] | None = None
    tools: list[TelnyxTool] | None = None


# Fields that distinguish Telnyx from other platforms
_TELNYX_SPECIFIC_FIELDS = frozenset(
    {
        "greeting",
        "voice_settings",
        "transcription",
        "telephony_settings",
        "dynamic_variables",
    }
)


class TelnyxImporter:
    """Import Telnyx AI assistant configurations."""

    @property
    def source_type(self) -> str:
        return "telnyx"

    def get_info(self) -> ImporterInfo:
        return ImporterInfo(
            source_type="telnyx",
            description="Import Telnyx AI assistant configurations",
            file_patterns=["*.json"],
        )

    def can_import(self, path_or_config: str | Path | dict) -> bool:
        """Detect Telnyx format by checking for characteristic fields."""
        try:
            config = self._load_config(path_or_config)
            return self._is_telnyx_config(config)
        except Exception:
            return False

    def _is_telnyx_config(self, config: dict) -> bool:
        """Check if config is a Telnyx AI assistant configuration."""
        # Telnyx requires instructions (string) and model (string)
        has_instructions = isinstance(config.get("instructions"), str) and bool(
            config.get("instructions")
        )
        has_model = isinstance(config.get("model"), str)

        if not (has_instructions and has_model):
            return False

        # Must have at least one Telnyx-specific field
        has_telnyx_fields = any(key in config for key in _TELNYX_SPECIFIC_FIELDS)

        if not has_telnyx_fields:
            return False

        # Exclude other platforms
        is_not_retell_llm = "general_prompt" not in config and "llm_id" not in config
        is_not_retell_cf = "start_node_id" not in config and "nodes" not in config
        # VAPI model is a dict, not a string
        is_not_vapi = not isinstance(config.get("model"), dict)
        # Bland uses "prompt" not "instructions"
        is_not_bland = "prompt" not in config or "instructions" in config

        return is_not_retell_llm and is_not_retell_cf and is_not_vapi and is_not_bland

    def import_agent(self, path_or_config: str | Path | dict) -> AgentGraph:
        """Convert Telnyx AI assistant config to AgentGraph."""
        raw_config = self._load_config(path_or_config)
        config = TelnyxAssistantConfig.model_validate(raw_config)

        tools, transitions = self._convert_tools(config.tools or [])

        node_id = "main"
        node_metadata: dict[str, Any] = {}
        if config.greeting:
            node_metadata["greeting"] = config.greeting

        nodes = {
            node_id: AgentNode(
                id=node_id,
                state_prompt=config.instructions,
                tools=tools,
                transitions=transitions,
                metadata=node_metadata,
            )
        }

        source_metadata = self._build_metadata(config)

        return AgentGraph(
            nodes=nodes,
            entry_node_id=node_id,
            source_type="telnyx",
            source_metadata=source_metadata,
            default_model=config.model,
        )

    def _convert_tools(
        self, tools: list[TelnyxTool]
    ) -> tuple[list[ToolDefinition], list[Transition]]:
        """Convert Telnyx tools to ToolDefinitions and Transitions.

        Handoff tools become Transitions; all others become ToolDefinitions.
        """
        tool_defs: list[ToolDefinition] = []
        transitions: list[Transition] = []

        for tool in tools:
            if tool.type == "handoff" and tool.handoff:
                for target in tool.handoff.ai_assistants:
                    transitions.append(
                        Transition(
                            target_node_id=target.id,
                            condition=TransitionCondition(
                                type="tool_call",
                                value=target.name,
                            ),
                            description=f"Handoff to {target.name}",
                        )
                    )
            elif tool.type == "webhook" and tool.webhook:
                webhook = tool.webhook
                parameters = self._merge_webhook_parameters(webhook)
                tool_defs.append(
                    ToolDefinition(
                        name=webhook.name,
                        description=webhook.description,
                        parameters=parameters,
                        type="custom",
                        url=webhook.url,
                    )
                )
            elif tool.type == "transfer":
                tool_defs.append(
                    ToolDefinition(
                        name="transfer",
                        description="Transfer the call",
                        parameters={
                            "transfer": (tool.transfer.model_dump() if tool.transfer else {})
                        },
                        type="transfer",
                    )
                )
            elif tool.type == "hangup":
                desc = ""
                if tool.hangup:
                    desc = tool.hangup.get("description", "")
                tool_defs.append(
                    ToolDefinition(
                        name="hangup",
                        description=desc or "End the call",
                        parameters={},
                        type="hangup",
                    )
                )

        return tool_defs, transitions

    def _merge_webhook_parameters(self, webhook: TelnyxWebhook) -> dict[str, Any]:
        """Merge path, query, and body parameters into a single schema."""
        # Use body_parameters as the primary schema if available
        if webhook.body_parameters:
            return webhook.body_parameters
        if webhook.path_parameters:
            return webhook.path_parameters
        if webhook.query_parameters:
            return webhook.query_parameters
        return {}

    def _build_metadata(self, config: TelnyxAssistantConfig) -> dict[str, Any]:
        """Build source metadata from Telnyx config."""
        metadata: dict[str, Any] = {}

        if config.name:
            metadata["name"] = config.name
        if config.id:
            metadata["assistant_id"] = config.id
        if config.model:
            metadata["model"] = config.model
        if config.greeting:
            metadata["greeting"] = config.greeting
        if config.voice_settings:
            metadata["voice_settings"] = config.voice_settings
        if config.transcription:
            metadata["transcription"] = config.transcription
        if config.telephony_settings:
            metadata["telephony_settings"] = config.telephony_settings
        if config.dynamic_variables:
            metadata["dynamic_variables"] = config.dynamic_variables

        return metadata

    def _load_config(self, path_or_config: str | Path | dict) -> dict[str, Any]:
        """Load config from path or return dict directly."""
        if isinstance(path_or_config, dict):
            return path_or_config
        path = Path(path_or_config)
        return json.loads(path.read_text())
