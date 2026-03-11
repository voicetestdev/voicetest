"""Tests for voicetest.importers.retell_llm module."""


class TestRetellLLMImporter:
    """Tests for Retell LLM JSON importer."""

    def test_source_type(self):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        assert importer.source_type == "retell-llm"

    def test_can_import_dict(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        assert importer.can_import(sample_retell_llm_config) is True

    def test_can_import_file_path(self, sample_retell_llm_config_path):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        assert importer.can_import(sample_retell_llm_config_path) is True
        assert importer.can_import(str(sample_retell_llm_config_path)) is True

    def test_can_import_rejects_conversation_flow(self, sample_retell_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        # Conversation Flow format should be rejected
        assert importer.can_import(sample_retell_config) is False

    def test_can_import_rejects_unknown(self):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        assert importer.can_import({"some": "config"}) is False
        assert importer.can_import({"model": "gpt-4"}) is False

    def test_import_agent_from_dict(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)

        assert graph.source_type == "retell-llm"
        assert graph.entry_node_id == "greeting"
        # 5 conversation nodes + 2 synthetic (end_call, transfer_to_nurse)
        assert len(graph.nodes) == 7
        assert "greeting" in graph.nodes
        assert "verify_identity" in graph.nodes
        assert "appointment_management" in graph.nodes
        assert "general_inquiry" in graph.nodes
        assert "closing" in graph.nodes
        assert "end_call" in graph.nodes
        assert "transfer_to_nurse" in graph.nodes

    def test_import_agent_from_path(self, sample_retell_llm_config_path):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config_path)

        assert graph.source_type == "retell-llm"
        assert graph.entry_node_id == "greeting"

    def test_state_instructions_include_general_prompt(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)

        greeting = graph.nodes["greeting"]
        # state_prompt contains just the state-specific prompt
        assert "Greet the patient" in greeting.state_prompt
        # general_prompt stored in source_metadata
        assert "medical receptionist" in graph.source_metadata.get("general_prompt", "")

    def test_transitions_imported(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)

        greeting = graph.nodes["greeting"]
        # 2 original edges + 2 synthetic (end_call, transfer_to_nurse)
        assert len(greeting.transitions) == 4

        targets = [t.target_node_id for t in greeting.transitions]
        assert "verify_identity" in targets
        assert "general_inquiry" in targets
        assert "end_call" in targets
        assert "transfer_to_nurse" in targets

    def test_transition_conditions_imported(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)

        greeting = graph.nodes["greeting"]
        verify_transition = next(
            t for t in greeting.transitions if t.target_node_id == "verify_identity"
        )
        assert verify_transition.condition.type == "llm_prompt"
        assert "appointment" in verify_transition.condition.value.lower()

    def test_tools_imported(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)

        verify_identity = graph.nodes["verify_identity"]
        assert verify_identity.tools is not None
        tool_names = [t.name for t in verify_identity.tools]
        # State-specific tool remains on the node
        assert "lookup_patient" in tool_names
        # Terminal tools moved to synthetic nodes
        assert "end_call" not in tool_names
        assert "transfer_to_nurse" not in tool_names
        # But edges to synthetic nodes exist
        targets = [t.target_node_id for t in verify_identity.transitions]
        assert "end_call" in targets
        assert "transfer_to_nurse" in targets

    def test_general_tools_on_all_states(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)

        # Terminal tools live on synthetic nodes, not conversation nodes
        # Conversation nodes should have edges to end_call instead
        conversation_nodes = [
            n for n in graph.nodes.values() if n.id not in ("end_call", "transfer_to_nurse")
        ]
        for node in conversation_nodes:
            targets = [t.target_node_id for t in node.transitions]
            assert "end_call" in targets, f"Node {node.id} should have edge to end_call"

    def test_source_metadata_captured(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)

        assert graph.source_metadata["llm_id"] == "llm_abc123def456"
        assert graph.source_metadata["model"] == "gpt-4o"
        assert "Hello!" in graph.source_metadata["begin_message"]

    def test_get_info(self):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        info = importer.get_info()

        assert info.source_type == "retell-llm"
        assert "Retell LLM" in info.description
        assert "*.json" in info.file_patterns

    def test_single_prompt_agent(self):
        """Test importing a single-prompt agent (no states)."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "llm_id": "llm_simple",
            "model": "gpt-4o-mini",
            "general_prompt": "You are a helpful assistant. Answer questions concisely.",
            "begin_message": "Hello! How can I help you?",
            "general_tools": [
                {"type": "end_call", "name": "end_call", "description": "End the call."}
            ],
            "states": [],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)

        assert graph.source_type == "retell-llm"
        assert graph.entry_node_id == "main"
        # main + synthetic end_call node
        assert len(graph.nodes) == 2
        assert "main" in graph.nodes
        assert "end_call" in graph.nodes
        assert "helpful assistant" in graph.nodes["main"].state_prompt
        # end_call tool moved to synthetic node; main has edge instead
        assert len(graph.nodes["main"].tools) == 0
        assert len(graph.nodes["main"].transitions) == 1
        assert graph.nodes["main"].transitions[0].target_node_id == "end_call"

    def test_tool_parameters_imported(self, sample_retell_llm_config):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)

        verify_identity = graph.nodes["verify_identity"]
        lookup_tool = next(t for t in verify_identity.tools if t.name == "lookup_patient")
        assert lookup_tool.parameters is not None
        assert "properties" in lookup_tool.parameters
        assert "full_name" in lookup_tool.parameters["properties"]


class TestRetellLLMDashboardExport:
    """Tests for Retell LLM dashboard export format (wrapped in retellLlmData)."""

    def test_can_import_wrapped_format(self, sample_retell_llm_dashboard_export):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        assert importer.can_import(sample_retell_llm_dashboard_export) is True

    def test_can_import_wrapped_format_path(self, sample_retell_llm_dashboard_export_path):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        assert importer.can_import(sample_retell_llm_dashboard_export_path) is True

    def test_import_agent_from_wrapped_format(self, sample_retell_llm_dashboard_export):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_dashboard_export)

        assert graph.source_type == "retell-llm"
        assert graph.entry_node_id == "greeting"
        # 5 conversation nodes + 2 synthetic (end_call, transfer_to_nurse)
        assert len(graph.nodes) == 7
        assert "greeting" in graph.nodes
        assert "verify_identity" in graph.nodes

    def test_wrapped_format_metadata(self, sample_retell_llm_dashboard_export):
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_dashboard_export)

        assert graph.source_metadata["llm_id"] == "llm_abc123def456"
        assert graph.source_metadata["model"] == "gpt-4o"

    def test_ambiguous_config_raises_error(self):
        """Config with LLM fields at both top level and in retellLlmData should error."""
        import pytest

        from voicetest.importers.retell_llm import RetellLLMImporter

        ambiguous_config = {
            "general_prompt": "Top level prompt",
            "retellLlmData": {
                "general_prompt": "Wrapped prompt",
                "llm_id": "llm_123",
            },
        }

        importer = RetellLLMImporter()
        with pytest.raises(ValueError, match="[Aa]mbiguous"):
            importer.import_agent(ambiguous_config)

    def test_ambiguous_config_can_import_returns_false(self):
        """can_import should return False for ambiguous configs."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        ambiguous_config = {
            "llm_id": "top_level_id",
            "retellLlmData": {
                "general_prompt": "Wrapped prompt",
            },
        }

        importer = RetellLLMImporter()
        assert importer.can_import(ambiguous_config) is False

    def test_end_call_tool_gets_correct_type(self):
        """Tools named end_call should become a synthetic node with type='end_call'."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "general_prompt": "You are a helpful agent.",
            "general_tools": [
                {"type": "custom", "name": "end_call", "description": ""},
            ],
            "states": [],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)
        # end_call tool is now on the synthetic node, not main
        tool = graph.nodes["end_call"].tools[0]
        assert tool.name == "end_call"
        assert tool.type == "end_call"

    def test_transfer_call_tool_gets_correct_type(self):
        """transfer_call_to_* tools should become synthetic nodes."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "general_prompt": "You are a helpful agent.",
            "general_tools": [
                {
                    "type": "custom",
                    "name": "transfer_call_to_person",
                    "description": "Transfer the call",
                },
            ],
            "states": [],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)
        # transfer tool is now on the synthetic node
        tool = graph.nodes["transfer_call_to_person"].tools[0]
        assert tool.name == "transfer_call_to_person"
        assert tool.type == "transfer_call"

    def test_custom_tool_keeps_custom_type(self):
        """Regular custom tools should keep type='custom'."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "general_prompt": "You are a helpful agent.",
            "general_tools": [
                {
                    "type": "custom",
                    "name": "lookup_patient",
                    "description": "Look up a patient",
                },
            ],
            "states": [],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)
        tool = graph.nodes["main"].tools[0]
        assert tool.name == "lookup_patient"
        assert tool.type == "custom"

    def test_end_call_tool_creates_synthetic_node(self):
        """end_call general tool should create a synthetic end_call node
        with edges only from nodes that have the end_call tool."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "general_prompt": "You are a helpful agent.",
            "general_tools": [
                {"type": "end_call", "name": "end_call", "description": "End the call."},
            ],
            "states": [
                {
                    "name": "greeting",
                    "state_prompt": "Greet the user.",
                    "edges": [],
                    "tools": [],
                },
                {
                    "name": "internal",
                    "state_prompt": "Internal routing.",
                    "edges": [],
                    "tools": [
                        {"type": "custom", "name": "lookup", "description": "Look up data."},
                    ],
                },
            ],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)

        # Synthetic end_call node should exist
        assert "end_call" in graph.nodes
        end_node = graph.nodes["end_call"]
        assert end_node.state_prompt == ""
        assert end_node.is_end_node() is True
        assert len(end_node.transitions) == 0

        # Nodes that had end_call tool should have edge to end_call
        for node_id in ("greeting", "internal"):
            node = graph.nodes[node_id]
            end_edges = [t for t in node.transitions if t.target_node_id == "end_call"]
            assert len(end_edges) == 1, f"Node {node_id} should have edge to end_call"
            assert end_edges[0].condition.type == "llm_prompt"
            assert "End the call" in end_edges[0].condition.value

        # end_call tool should be stripped from conversation nodes
        for node_id in ("greeting", "internal"):
            tool_types = [t.type for t in graph.nodes[node_id].tools]
            assert "end_call" not in tool_types

    def test_transfer_call_tool_creates_synthetic_node(self):
        """transfer_call general tool should create a synthetic transfer node with edges."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "general_prompt": "You are a helpful agent.",
            "general_tools": [
                {
                    "type": "transfer_call",
                    "name": "transfer_to_nurse",
                    "description": "Transfer to a nurse.",
                },
            ],
            "states": [
                {
                    "name": "greeting",
                    "state_prompt": "Greet the user.",
                    "edges": [],
                    "tools": [],
                },
            ],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)

        assert "transfer_to_nurse" in graph.nodes
        transfer_node = graph.nodes["transfer_to_nurse"]
        assert transfer_node.state_prompt == ""
        assert transfer_node.is_transfer_node() is True

        greeting = graph.nodes["greeting"]
        transfer_edges = [
            t for t in greeting.transitions if t.target_node_id == "transfer_to_nurse"
        ]
        assert len(transfer_edges) == 1

    def test_end_call_single_prompt_agent(self):
        """Single-prompt agent with end_call should get synthetic end_call node."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "general_prompt": "You are a helpful assistant.",
            "general_tools": [
                {"type": "end_call", "name": "end_call", "description": "End the call."},
            ],
            "states": [],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)

        assert "end_call" in graph.nodes
        assert "main" in graph.nodes
        main_node = graph.nodes["main"]
        end_edges = [t for t in main_node.transitions if t.target_node_id == "end_call"]
        assert len(end_edges) == 1

    def test_node_without_end_call_tool_gets_no_edge(self):
        """Nodes that don't have end_call tool should NOT get an edge to end_call."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "general_prompt": "You are a helpful agent.",
            "general_tools": [],
            "states": [
                {
                    "name": "greeting",
                    "state_prompt": "Greet the user.",
                    "edges": [],
                    "tools": [
                        {"type": "end_call", "name": "end_call", "description": "End the call."},
                    ],
                },
                {
                    "name": "router",
                    "state_prompt": "Route the user.",
                    "edges": [],
                    "tools": [],
                },
            ],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)

        # greeting had end_call tool -> should have edge
        greeting = graph.nodes["greeting"]
        end_edges = [t for t in greeting.transitions if t.target_node_id == "end_call"]
        assert len(end_edges) == 1

        # router had no end_call tool -> no edge
        router = graph.nodes["router"]
        end_edges = [t for t in router.transitions if t.target_node_id == "end_call"]
        assert len(end_edges) == 0

    def test_extract_agent_envelope(self):
        """_extract_agent_envelope filters LLM keys, keeps agent fields."""
        from voicetest.importers.retell_llm import _extract_agent_envelope

        config = {
            "voice_id": "voice_abc",
            "language": "en-US",
            "agent_name": "My Agent",
            "general_prompt": "You are helpful.",
            "llm_id": "llm_123",
            "model": "gpt-4o",
            "begin_message": "Hello!",
            "general_tools": [],
            "states": [],
            "retellLlmData": {"nested": "data"},
        }

        envelope = _extract_agent_envelope(config)
        assert envelope["voice_id"] == "voice_abc"
        assert envelope["language"] == "en-US"
        assert envelope["agent_name"] == "My Agent"
        # LLM keys should be filtered out
        assert "general_prompt" not in envelope
        assert "llm_id" not in envelope
        assert "model" not in envelope
        assert "begin_message" not in envelope
        assert "general_tools" not in envelope
        assert "states" not in envelope
        assert "retellLlmData" not in envelope

    def test_agent_envelope_stored_in_metadata(self):
        """Full agent export -> agent_envelope in source_metadata."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        config = {
            "voice_id": "voice_xyz",
            "language": "ja-JP",
            "general_prompt": "You are a helpful agent.",
            "model": "gpt-4o",
            "general_tools": [],
            "states": [
                {
                    "name": "main",
                    "state_prompt": "Help the user.",
                    "edges": [],
                    "tools": [],
                },
            ],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(config)

        assert "agent_envelope" in graph.source_metadata
        envelope = graph.source_metadata["agent_envelope"]
        assert envelope["voice_id"] == "voice_xyz"
        assert envelope["language"] == "ja-JP"
        assert "general_prompt" not in envelope
