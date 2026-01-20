"""Tests for the VAPI importer."""

from pathlib import Path

from voicetest.importers.vapi import VapiImporter


class TestVapiImporterDetection:
    """Test VAPI format detection."""

    def test_can_import_vapi_assistant(self, sample_vapi_assistant: dict):
        """Detect VAPI assistant format."""
        importer = VapiImporter()
        assert importer.can_import(sample_vapi_assistant)

    def test_can_import_vapi_simple(self, sample_vapi_assistant_simple: dict):
        """Detect simple VAPI assistant format."""
        importer = VapiImporter()
        assert importer.can_import(sample_vapi_assistant_simple)

    def test_can_import_from_path(self, sample_vapi_assistant_path: Path):
        """Detect VAPI format from file path."""
        importer = VapiImporter()
        assert importer.can_import(sample_vapi_assistant_path)

    def test_rejects_retell_llm_format(self, sample_retell_llm_config: dict):
        """Reject Retell LLM format."""
        importer = VapiImporter()
        assert not importer.can_import(sample_retell_llm_config)

    def test_rejects_retell_cf_format(self, sample_retell_config: dict):
        """Reject Retell Conversation Flow format."""
        importer = VapiImporter()
        assert not importer.can_import(sample_retell_config)

    def test_rejects_empty_config(self):
        """Reject empty configuration."""
        importer = VapiImporter()
        assert not importer.can_import({})

    def test_rejects_invalid_input(self):
        """Reject invalid input gracefully."""
        importer = VapiImporter()
        assert not importer.can_import("/nonexistent/path.json")


class TestVapiImporterConversion:
    """Test VAPI to AgentGraph conversion."""

    def test_import_creates_single_node(self, sample_vapi_assistant: dict):
        """VAPI imports create a single node."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)

        assert len(graph.nodes) == 1
        assert "main" in graph.nodes
        assert graph.entry_node_id == "main"

    def test_import_extracts_system_prompt(self, sample_vapi_assistant: dict):
        """System prompt is extracted from model.messages."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)

        node = graph.nodes["main"]
        assert "medical receptionist" in node.instructions.lower()
        assert "Acme Healthcare" in node.instructions

    def test_import_extracts_tools(self, sample_vapi_assistant: dict):
        """Tools are extracted from VAPI format."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)

        node = graph.nodes["main"]
        tool_names = {t.name for t in node.tools}
        assert "lookup_patient" in tool_names
        assert "book_appointment" in tool_names
        assert "get_available_slots" in tool_names
        assert "transfer_call" in tool_names
        assert "end_call" in tool_names

    def test_import_tool_parameters(self, sample_vapi_assistant: dict):
        """Tool parameters are preserved."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)

        node = graph.nodes["main"]
        lookup_tool = next(t for t in node.tools if t.name == "lookup_patient")
        assert lookup_tool.parameters is not None
        assert "properties" in lookup_tool.parameters
        assert "full_name" in lookup_tool.parameters["properties"]

    def test_import_preserves_metadata(self, sample_vapi_assistant: dict):
        """Source metadata is preserved."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)

        assert graph.source_type == "vapi"
        assert graph.source_metadata.get("assistant_id") == "asst_abc123def456"
        assert graph.source_metadata.get("name") == "Healthcare Receptionist"
        assert graph.source_metadata.get("first_message") is not None
        assert "Acme Healthcare" in graph.source_metadata["first_message"]

    def test_import_preserves_model_config(self, sample_vapi_assistant: dict):
        """Model configuration is preserved in metadata."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)

        assert graph.source_metadata.get("model_provider") == "openai"
        assert graph.source_metadata.get("model") == "gpt-4o"
        assert graph.source_metadata.get("temperature") == 0.7

    def test_import_preserves_voice_config(self, sample_vapi_assistant: dict):
        """Voice configuration is preserved in metadata."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)

        assert graph.source_metadata.get("voice_provider") == "11labs"
        assert graph.source_metadata.get("voice_id") == "sarah"

    def test_import_preserves_transcriber_config(self, sample_vapi_assistant: dict):
        """Transcriber configuration is preserved in metadata."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)

        assert graph.source_metadata.get("transcriber_provider") == "deepgram"
        assert graph.source_metadata.get("transcriber_model") == "nova-2"
        assert graph.source_metadata.get("transcriber_language") == "en"

    def test_import_simple_assistant(self, sample_vapi_assistant_simple: dict):
        """Import simple assistant without tools."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant_simple)

        assert len(graph.nodes) == 1
        node = graph.nodes["main"]
        assert "friendly greeter" in node.instructions.lower()
        assert len(node.tools) == 0

    def test_import_from_path(self, sample_vapi_assistant_path: Path):
        """Import from file path."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant_path)

        assert graph.source_type == "vapi"
        assert len(graph.nodes) == 1


class TestVapiSquadImport:
    """Test VAPI squad import."""

    def test_can_import_squad(self, sample_vapi_squad: dict):
        """Detect VAPI squad format."""
        importer = VapiImporter()
        assert importer.can_import(sample_vapi_squad)

    def test_can_import_squad_from_path(self, sample_vapi_squad_path: Path):
        """Detect VAPI squad format from file path."""
        importer = VapiImporter()
        assert importer.can_import(sample_vapi_squad_path)

    def test_import_squad_creates_multiple_nodes(self, sample_vapi_squad: dict):
        """Squad imports create multiple nodes."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_squad)

        # Squad has 5 members
        assert len(graph.nodes) == 5
        assert "Greeting" in graph.nodes
        assert "Verify Identity" in graph.nodes
        assert "Appointment Management" in graph.nodes
        assert "General Inquiry" in graph.nodes
        assert "Closing" in graph.nodes

    def test_import_squad_entry_node(self, sample_vapi_squad: dict):
        """First squad member becomes entry node."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_squad)

        assert graph.entry_node_id == "Greeting"

    def test_import_squad_transitions(self, sample_vapi_squad: dict):
        """Handoff tools become transitions."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_squad)

        greeting_node = graph.nodes["Greeting"]
        assert len(greeting_node.transitions) == 2

        transition_targets = {t.target_node_id for t in greeting_node.transitions}
        assert "Verify Identity" in transition_targets
        assert "General Inquiry" in transition_targets

    def test_import_squad_tools(self, sample_vapi_squad: dict):
        """Regular tools are preserved."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_squad)

        verify_node = graph.nodes["Verify Identity"]
        tool_names = {t.name for t in verify_node.tools}
        assert "lookup_patient" in tool_names

        appt_node = graph.nodes["Appointment Management"]
        tool_names = {t.name for t in appt_node.tools}
        assert "get_available_slots" in tool_names
        assert "book_appointment" in tool_names

    def test_import_squad_metadata(self, sample_vapi_squad: dict):
        """Squad metadata is preserved."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_squad)

        assert graph.source_type == "vapi"
        assert graph.source_metadata.get("is_squad") is True
        assert graph.source_metadata.get("squad_id") == "squad_healthcare_123"
        assert graph.source_metadata.get("name") == "Healthcare Squad"

    def test_import_squad_first_message(self, sample_vapi_squad: dict):
        """First message is stored in node metadata."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_squad)

        greeting_node = graph.nodes["Greeting"]
        assert greeting_node.metadata.get("first_message") is not None
        assert "Acme Healthcare" in greeting_node.metadata["first_message"]


class TestVapiImporterInfo:
    """Test importer metadata."""

    def test_source_type(self):
        """Source type is 'vapi'."""
        importer = VapiImporter()
        assert importer.source_type == "vapi"

    def test_get_info(self):
        """get_info returns correct metadata."""
        importer = VapiImporter()
        info = importer.get_info()

        assert info.source_type == "vapi"
        assert "VAPI" in info.description
        assert "*.json" in info.file_patterns
