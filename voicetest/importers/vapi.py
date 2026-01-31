"""VAPI assistant and squad JSON importer."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    ToolDefinition,
    Transition,
    TransitionCondition,
)


class VapiToolFunction(BaseModel):
    """VAPI tool function definition."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    parameters: dict[str, Any] | None = None


class VapiHandoffDestination(BaseModel):
    """VAPI handoff destination."""

    model_config = ConfigDict(extra="ignore")

    type: str = "assistant"
    assistant_name: str | None = Field(default=None, alias="assistantName")
    assistant_id: str | None = Field(default=None, alias="assistantId")
    description: str = ""
    message: str = ""


class VapiTool(BaseModel):
    """VAPI tool definition."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    type: str = "function"
    function: VapiToolFunction | None = None
    server: dict[str, Any] | None = None
    destinations: list[VapiHandoffDestination] = Field(default_factory=list)


class VapiModelMessage(BaseModel):
    """VAPI model message."""

    model_config = ConfigDict(extra="ignore")

    role: str
    content: str


class VapiModel(BaseModel):
    """VAPI model configuration."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    provider: str = "openai"
    model: str = "gpt-4o"
    messages: list[VapiModelMessage] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = Field(default=None, alias="maxTokens")
    tools: list[VapiTool] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list, alias="toolIds")

    @field_validator("tools", "tool_ids", "messages", mode="before")
    @classmethod
    def list_default(cls, v):
        return v if v is not None else []


class VapiVoice(BaseModel):
    """VAPI voice configuration."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    provider: str = ""
    voice_id: str = Field(default="", alias="voiceId")


class VapiTranscriber(BaseModel):
    """VAPI transcriber configuration."""

    model_config = ConfigDict(extra="ignore")

    provider: str = "deepgram"
    model: str = ""
    language: str = "en"


class VapiAssistant(BaseModel):
    """VAPI assistant configuration."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = None
    name: str = ""
    model: VapiModel | None = None
    voice: VapiVoice | None = None
    transcriber: VapiTranscriber | None = None
    first_message: str | None = Field(default=None, alias="firstMessage")
    tools: list[VapiTool] = Field(default_factory=list)
    silence_timeout_seconds: int | None = Field(default=None, alias="silenceTimeoutSeconds")
    max_duration_seconds: int | None = Field(default=None, alias="maxDurationSeconds")


class VapiSquadMember(BaseModel):
    """VAPI squad member."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    assistant_id: str | None = Field(default=None, alias="assistantId")
    assistant: VapiAssistant | None = None
    assistant_destinations: list[VapiHandoffDestination] = Field(
        default_factory=list, alias="assistantDestinations"
    )


class VapiSquad(BaseModel):
    """VAPI squad configuration."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str = ""
    members: list[VapiSquadMember] = Field(default_factory=list)


class VapiImporter:
    """Import VAPI assistant or squad JSON."""

    @property
    def source_type(self) -> str:
        return "vapi"

    def get_info(self) -> ImporterInfo:
        return ImporterInfo(
            source_type="vapi",
            description="Import VAPI assistant or squad JSON exports",
            file_patterns=["*.json"],
        )

    def can_import(self, path_or_config: str | Path | dict) -> bool:
        """Detect VAPI format by checking for characteristic fields."""
        try:
            config = self._load_config(path_or_config)

            # Check for squad format (has members array)
            if "members" in config and isinstance(config.get("members"), list):
                return self._is_vapi_squad(config)

            # Check for single assistant format
            return self._is_vapi_assistant(config)
        except Exception:
            return False

    def _is_vapi_squad(self, config: dict) -> bool:
        """Check if config is a VAPI squad."""
        members = config.get("members", [])
        if not members:
            return False

        # Check first member has assistant or assistantId
        first_member = members[0]
        return "assistant" in first_member or "assistantId" in first_member

    def _is_vapi_assistant(self, config: dict) -> bool:
        """Check if config is a VAPI assistant."""
        has_model = "model" in config and isinstance(config.get("model"), dict)
        has_messages = has_model and "messages" in config.get("model", {})
        has_first_message = "firstMessage" in config
        has_vapi_tools = "tools" in config and isinstance(config.get("tools"), list)

        # Check tool structure is VAPI style (has function.name or type=handoff)
        if has_vapi_tools and config.get("tools"):
            first_tool = config["tools"][0]
            has_vapi_tool_structure = isinstance(first_tool, dict) and (
                ("function" in first_tool and isinstance(first_tool.get("function"), dict))
                or first_tool.get("type") == "handoff"
            )
        else:
            has_vapi_tool_structure = True

        # Distinguish from Retell formats
        is_not_retell_llm = "general_prompt" not in config and "llm_id" not in config
        is_not_retell_cf = "start_node_id" not in config and "nodes" not in config

        return (
            (has_messages or has_first_message)
            and has_vapi_tool_structure
            and is_not_retell_llm
            and is_not_retell_cf
        )

    def import_agent(self, path_or_config: str | Path | dict) -> AgentGraph:
        """Convert VAPI assistant or squad JSON to AgentGraph."""
        raw_config = self._load_config(path_or_config)

        # Check if this is a squad
        if "members" in raw_config and isinstance(raw_config.get("members"), list):
            return self._import_squad(raw_config)

        # Single assistant
        return self._import_assistant(raw_config)

    def _import_assistant(self, raw_config: dict) -> AgentGraph:
        """Import a single VAPI assistant."""
        assistant = VapiAssistant.model_validate(raw_config)

        # Extract system prompt from model.messages
        system_prompt = self._extract_system_prompt(assistant)

        # Get all tools (from both assistant.tools and model.tools)
        all_tools = list(assistant.tools)
        if assistant.model and assistant.model.tools:
            all_tools.extend(assistant.model.tools)

        # Convert tools, extracting handoffs as transitions
        tools, transitions = self._process_tools(all_tools)

        # Create single node
        nodes = {
            "main": AgentNode(
                id="main",
                state_prompt=system_prompt,
                tools=tools,
                transitions=transitions,
            )
        }

        # Build source metadata
        source_metadata = self._build_assistant_metadata(assistant)
        source_metadata["general_prompt"] = ""  # VAPI has no separate general prompt

        return AgentGraph(
            nodes=nodes,
            entry_node_id="main",
            source_type="vapi",
            source_metadata=source_metadata,
        )

    def _import_squad(self, raw_config: dict) -> AgentGraph:
        """Import a VAPI squad as multi-node graph."""
        squad = VapiSquad.model_validate(raw_config)

        nodes: dict[str, AgentNode] = {}
        entry_node_id: str | None = None
        assistant_names: dict[str, str] = {}  # Map assistant IDs to names

        # First pass: create nodes and build name mapping
        for i, member in enumerate(squad.members):
            assistant = member.assistant
            if not assistant:
                # Skip members that reference external assistants by ID only
                if member.assistant_id:
                    assistant_names[member.assistant_id] = member.assistant_id
                continue

            node_id = assistant.name or f"assistant_{i}"
            if assistant.id:
                assistant_names[assistant.id] = node_id
            assistant_names[assistant.name] = node_id

            # Extract system prompt
            system_prompt = self._extract_system_prompt(assistant)

            # Get all tools
            all_tools = list(assistant.tools)
            if assistant.model and assistant.model.tools:
                all_tools.extend(assistant.model.tools)

            # Convert tools, extracting handoffs as transitions
            tools, transitions = self._process_tools(all_tools)

            # Add transitions from member-level assistantDestinations
            for dest in member.assistant_destinations:
                target = dest.assistant_name or dest.assistant_id or ""
                if target:
                    transitions.append(
                        Transition(
                            target_node_id=target,
                            condition=TransitionCondition(
                                type="llm_prompt",
                                value=dest.description,
                            ),
                            description=dest.description,
                        )
                    )

            nodes[node_id] = AgentNode(
                id=node_id,
                state_prompt=system_prompt,
                tools=tools,
                transitions=transitions,
                metadata={"first_message": assistant.first_message}
                if assistant.first_message
                else {},
            )

            # First member is entry node
            if entry_node_id is None:
                entry_node_id = node_id

        # Second pass: resolve transition targets to actual node IDs
        for node in nodes.values():
            for transition in node.transitions:
                if transition.target_node_id in assistant_names:
                    transition.target_node_id = assistant_names[transition.target_node_id]

        # Build source metadata
        source_metadata: dict[str, Any] = {
            "is_squad": True,
            "general_prompt": "",  # VAPI has no separate general prompt
        }
        if squad.id:
            source_metadata["squad_id"] = squad.id
        if squad.name:
            source_metadata["name"] = squad.name

        return AgentGraph(
            nodes=nodes,
            entry_node_id=entry_node_id or "main",
            source_type="vapi",
            source_metadata=source_metadata,
        )

    def _extract_system_prompt(self, assistant: VapiAssistant) -> str:
        """Extract system prompt from assistant's model.messages."""
        if assistant.model and assistant.model.messages:
            for msg in assistant.model.messages:
                if msg.role == "system":
                    return msg.content
        return ""

    def _process_tools(
        self, tools: list[VapiTool]
    ) -> tuple[list[ToolDefinition], list[Transition]]:
        """Process tools, separating regular tools from handoff transitions."""
        regular_tools: list[ToolDefinition] = []
        transitions: list[Transition] = []

        for tool in tools:
            if tool.type == "handoff":
                # Handoff tool becomes transitions
                for dest in tool.destinations:
                    target = dest.assistant_name or dest.assistant_id or ""
                    if target:
                        transitions.append(
                            Transition(
                                target_node_id=target,
                                condition=TransitionCondition(
                                    type="llm_prompt",
                                    value=dest.description,
                                ),
                                description=dest.description,
                            )
                        )
            elif tool.function:
                # Regular function tool
                regular_tools.append(
                    ToolDefinition(
                        name=tool.function.name,
                        description=tool.function.description,
                        parameters=tool.function.parameters or {},
                    )
                )

        return regular_tools, transitions

    def _build_assistant_metadata(self, assistant: VapiAssistant) -> dict[str, Any]:
        """Build source metadata from assistant config."""
        metadata: dict[str, Any] = {}
        if assistant.id:
            metadata["assistant_id"] = assistant.id
        if assistant.name:
            metadata["name"] = assistant.name
        if assistant.first_message:
            metadata["first_message"] = assistant.first_message
        if assistant.model:
            metadata["model_provider"] = assistant.model.provider
            metadata["model"] = assistant.model.model
            if assistant.model.temperature is not None:
                metadata["temperature"] = assistant.model.temperature
            if assistant.model.max_tokens is not None:
                metadata["max_tokens"] = assistant.model.max_tokens
        if assistant.voice:
            metadata["voice_provider"] = assistant.voice.provider
            metadata["voice_id"] = assistant.voice.voice_id
        if assistant.transcriber:
            metadata["transcriber_provider"] = assistant.transcriber.provider
            metadata["transcriber_model"] = assistant.transcriber.model
            metadata["transcriber_language"] = assistant.transcriber.language
        return metadata

    def _load_config(self, path_or_config: str | Path | dict) -> dict[str, Any]:
        """Load config from path or return dict directly."""
        if isinstance(path_or_config, dict):
            return path_or_config
        path = Path(path_or_config)
        return json.loads(path.read_text())
