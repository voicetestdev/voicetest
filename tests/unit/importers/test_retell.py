"""Tests for voicetest.importers.retell module."""

from pathlib import Path

import pytest

from voicetest.importers.retell import RetellImporter


class TestRetellImporter:
    """Tests for Retell JSON importer."""

    def test_source_type(self):
        importer = RetellImporter()
        assert importer.source_type == "retell"

    def test_can_import_dict(self, sample_retell_config):
        importer = RetellImporter()
        assert importer.can_import(sample_retell_config) is True

    def test_can_import_file_path(self, sample_retell_config_path):
        importer = RetellImporter()
        assert importer.can_import(sample_retell_config_path) is True
        assert importer.can_import(str(sample_retell_config_path)) is True

    def test_can_import_rejects_non_retell(self):
        importer = RetellImporter()
        # Missing required fields
        assert importer.can_import({"some": "config"}) is False
        assert importer.can_import({"nodes": []}) is False  # Missing start_node_id
        assert importer.can_import({"start_node_id": "x"}) is False  # Missing nodes

    def test_import_agent_from_dict(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 4
        assert "greeting" in graph.nodes
        assert "billing" in graph.nodes
        assert "support" in graph.nodes
        assert "end_call" in graph.nodes

    def test_import_agent_from_path(self, sample_retell_config_path):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_path)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"

    def test_node_instructions_imported(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert "Greet the customer" in greeting.state_prompt

        billing = graph.nodes["billing"]
        assert "billing inquiry" in billing.state_prompt

    def test_transitions_imported(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert len(greeting.transitions) == 2

        targets = [t.target_node_id for t in greeting.transitions]
        assert "billing" in targets
        assert "support" in targets

    def test_transition_conditions_imported(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        billing_transition = next(t for t in greeting.transitions if t.target_node_id == "billing")
        assert billing_transition.condition.type == "llm_prompt"
        assert "billing" in billing_transition.condition.value.lower()

    def test_source_metadata_captured(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        assert graph.source_metadata["conversation_flow_id"] == "test-flow-001"

    def test_node_metadata_captured(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert greeting.metadata["retell_type"] == "conversation"

    def test_get_info(self):
        importer = RetellImporter()
        info = importer.get_info()

        assert info.source_type == "retell"
        assert "Retell" in info.description
        assert "*.json" in info.file_patterns


class TestRetellImporterComplex:
    """Tests for Retell importer with complex configuration including tools."""

    def test_import_complex_config(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 11

    def test_tools_imported(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        greeting = graph.nodes["greeting"]
        assert greeting.tools is not None
        assert len(greeting.tools) == 6

        tool_names = [t.name for t in greeting.tools]
        assert "lookup_patient" in tool_names
        assert "get_available_slots" in tool_names
        assert "book_appointment" in tool_names
        assert "cancel_appointment" in tool_names
        assert "end_call" in tool_names
        assert "transfer_to_nurse" in tool_names

    def test_tool_parameters_imported(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        greeting = graph.nodes["greeting"]
        lookup_tool = next(t for t in greeting.tools if t.name == "lookup_patient")
        assert lookup_tool.parameters is not None
        assert "properties" in lookup_tool.parameters
        assert "full_name" in lookup_tool.parameters["properties"]
        assert "date_of_birth" in lookup_tool.parameters["properties"]

    def test_global_prompt_stored_separately(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        greeting = graph.nodes["greeting"]
        # state_prompt has only node-specific instructions
        assert "Greet the caller warmly" in greeting.state_prompt
        # general_prompt stored in source_metadata (not merged)
        assert "professional medical receptionist" in graph.source_metadata.get(
            "general_prompt", ""
        )

    def test_source_metadata_includes_model_settings(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        assert graph.source_metadata["conversation_flow_id"] == "cf_healthcare_001"
        assert graph.source_metadata["version"] == 2
        assert graph.source_metadata["model_temperature"] == 0.7
        assert graph.source_metadata["tool_call_strict_mode"] is True
        assert graph.source_metadata["start_speaker"] == "agent"

    def test_source_metadata_includes_model_choice(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        model_choice = graph.source_metadata["model_choice"]
        assert model_choice["type"] == "cascading"
        assert model_choice["model"] == "gpt-4.1"
        assert model_choice["high_priority"] is True

    def test_source_metadata_includes_knowledge_bases(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        kb_ids = graph.source_metadata["knowledge_base_ids"]
        assert "kb_office_policies" in kb_ids
        assert "kb_insurance_info" in kb_ids

    def test_source_metadata_includes_dynamic_variables(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        vars = graph.source_metadata["default_dynamic_variables"]
        assert vars["office_name"] == "Acme Healthcare"
        assert vars["office_hours"] == "Monday-Friday 8am-6pm"
        assert vars["office_phone"] == "555-123-4567"

    def test_all_nodes_have_same_tools(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        for node in graph.nodes.values():
            assert len(node.tools) == 6


class TestRetellImporterTransferMetadata:
    """Tests for CF importer preserving transfer tool metadata."""

    def test_cf_importer_preserves_transfer_metadata(self):
        """CF import with transfer_call tool -> transfer_destination in tool metadata."""
        from voicetest.importers.retell import RetellImporter

        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Help the user."},
                    "edges": [],
                },
            ],
            "tools": [
                {
                    "type": "transfer_call",
                    "name": "transfer_to_billing",
                    "description": "Transfer to billing",
                    "transfer_destination": {
                        "type": "predefined",
                        "number": "+18005551234",
                    },
                    "transfer_option": {
                        "type": "warm_transfer",
                        "agent_detection_timeout_ms": 30000,
                    },
                },
            ],
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        main_node = graph.nodes["main"]
        transfer_tool = next(t for t in main_node.tools if t.name == "transfer_to_billing")
        assert transfer_tool.metadata["transfer_destination"]["number"] == "+18005551234"
        assert transfer_tool.metadata["transfer_option"]["type"] == "warm_transfer"


class TestRetellImporterDisplayPosition:
    """Tests for importing display_position data from Retell CF."""

    def test_display_position_preserved_on_import(self):
        """Nodes with display_position in JSON have it stored in metadata."""
        config = {
            "start_node_id": "greeting",
            "nodes": [
                {
                    "id": "greeting",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hello."},
                    "edges": [],
                    "display_position": {"x": 100, "y": 200},
                },
                {
                    "id": "farewell",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Bye."},
                    "edges": [],
                    "display_position": {"x": 600, "y": 200},
                },
            ],
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        assert graph.nodes["greeting"].metadata["display_position"] == {"x": 100, "y": 200}
        assert graph.nodes["farewell"].metadata["display_position"] == {"x": 600, "y": 200}

    def test_display_position_absent_not_in_metadata(self):
        """Nodes without display_position don't have it in metadata."""
        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hi."},
                    "edges": [],
                },
            ],
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        assert "display_position" not in graph.nodes["main"].metadata

    def test_begin_tag_display_position_preserved(self):
        """begin_tag_display_position at flow level is stored in source_metadata."""
        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hi."},
                    "edges": [],
                },
            ],
            "begin_tag_display_position": {"x": -150, "y": 0},
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        assert graph.source_metadata["begin_tag_display_position"] == {"x": -150, "y": 0}

    def test_begin_tag_display_position_absent(self):
        """When begin_tag_display_position is missing, it's not in source_metadata."""
        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hi."},
                    "edges": [],
                },
            ],
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        assert "begin_tag_display_position" not in graph.source_metadata


class TestRetellImporterLogicSplit:
    """Tests for Retell CF importer handling logic split nodes (no instruction)."""

    def test_import_config_with_logic_split(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 5

    def test_logic_split_node_has_empty_prompt(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        router = graph.nodes["router"]
        assert router.state_prompt == ""

    def test_logic_split_node_preserves_type_metadata(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        router = graph.nodes["router"]
        assert router.metadata["retell_type"] == "logic_split"
        assert router.metadata["name"] == "Account Type Router"

    def test_logic_split_node_preserves_display_position(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        router = graph.nodes["router"]
        assert router.metadata["display_position"] == {"x": 300, "y": 150}

    def test_logic_split_edges_imported(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        router = graph.nodes["router"]
        assert len(router.transitions) == 2
        targets = {t.target_node_id for t in router.transitions}
        assert targets == {"premium_support", "standard_support"}

    def test_logic_split_edge_conditions_are_equations(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        router = graph.nodes["router"]
        for transition in router.transitions:
            assert transition.condition.type == "equation"

    def test_logic_split_equation_clauses_preserved(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        router = graph.nodes["router"]
        premium_transition = next(
            t for t in router.transitions if t.target_node_id == "premium_support"
        )
        assert len(premium_transition.condition.equations) == 1
        clause = premium_transition.condition.equations[0]
        assert clause.left == "account_type"
        assert clause.operator == "=="
        assert clause.right == "premium"

    def test_logic_split_equation_value_readable(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        router = graph.nodes["router"]
        premium_transition = next(
            t for t in router.transitions if t.target_node_id == "premium_support"
        )
        assert "account_type" in premium_transition.condition.value
        assert "premium" in premium_transition.condition.value

    def test_logic_split_from_file_path(self, sample_retell_config_logic_split_path):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split_path)

        assert "router" in graph.nodes
        assert graph.nodes["router"].state_prompt == ""

    def test_conversation_nodes_unaffected(self, sample_retell_config_logic_split):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_logic_split)

        assert "Greet the caller" in graph.nodes["greeting"].state_prompt
        assert "premium-tier" in graph.nodes["premium_support"].state_prompt
        assert "standard support" in graph.nodes["standard_support"].state_prompt.lower()
        assert "Thank the caller" in graph.nodes["farewell"].state_prompt


class TestRetellImporterElseEdge:
    """Tests for Retell CF importer handling else_edge on logic/branch nodes."""

    def test_else_edge_imported_as_always_transition(self):
        config = {
            "start_node_id": "greeting",
            "nodes": [
                {
                    "id": "greeting",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hello."},
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "router",
                            "transition_condition": {"type": "prompt", "prompt": "Ready"},
                        }
                    ],
                },
                {
                    "id": "router",
                    "type": "branch",
                    "edges": [
                        {
                            "id": "edge-2",
                            "destination_node_id": "premium",
                            "transition_condition": {
                                "type": "equation",
                                "equations": [
                                    {"left": "tier", "operator": "==", "right": "premium"}
                                ],
                            },
                        },
                    ],
                    "else_edge": {
                        "id": "edge-else",
                        "destination_node_id": "fallback",
                        "transition_condition": {
                            "type": "prompt",
                            "prompt": "Else",
                        },
                    },
                },
                {
                    "id": "premium",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Premium."},
                    "edges": [],
                },
                {
                    "id": "fallback",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Fallback."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        router = graph.nodes["router"]
        assert len(router.transitions) == 2

        else_transition = router.transitions[-1]
        assert else_transition.target_node_id == "fallback"
        assert else_transition.condition.type == "always"

    def test_else_edge_appended_after_equation_edges(self):
        config = {
            "start_node_id": "router",
            "nodes": [
                {
                    "id": "router",
                    "type": "branch",
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "a",
                            "transition_condition": {
                                "type": "equation",
                                "equations": [{"left": "x", "operator": "==", "right": "1"}],
                            },
                        },
                        {
                            "id": "edge-2",
                            "destination_node_id": "b",
                            "transition_condition": {
                                "type": "equation",
                                "equations": [{"left": "x", "operator": "==", "right": "2"}],
                            },
                        },
                    ],
                    "else_edge": {
                        "id": "edge-else",
                        "destination_node_id": "c",
                        "transition_condition": {"type": "prompt", "prompt": "Else"},
                    },
                },
                {
                    "id": "a",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "A."},
                    "edges": [],
                },
                {
                    "id": "b",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "B."},
                    "edges": [],
                },
                {
                    "id": "c",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "C."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        router = graph.nodes["router"]
        assert len(router.transitions) == 3
        assert router.transitions[0].condition.type == "equation"
        assert router.transitions[1].condition.type == "equation"
        assert router.transitions[2].condition.type == "always"
        assert router.transitions[2].target_node_id == "c"


class TestRetellImporterMustacheStripping:
    """Tests for stripping {{}} from equation variable names during import."""

    def test_mustache_stripped_from_equation_left(self):
        config = {
            "start_node_id": "router",
            "nodes": [
                {
                    "id": "router",
                    "type": "branch",
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "target",
                            "transition_condition": {
                                "type": "equation",
                                "equations": [
                                    {
                                        "left": "{{patient_is_minor}}",
                                        "operator": "==",
                                        "right": "True",
                                    }
                                ],
                            },
                        },
                    ],
                },
                {
                    "id": "target",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Target."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        clause = graph.nodes["router"].transitions[0].condition.equations[0]
        assert clause.left == "patient_is_minor"

    def test_mustache_stripped_from_equation_right(self):
        config = {
            "start_node_id": "router",
            "nodes": [
                {
                    "id": "router",
                    "type": "branch",
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "target",
                            "transition_condition": {
                                "type": "equation",
                                "equations": [
                                    {
                                        "left": "status",
                                        "operator": "==",
                                        "right": "{{expected_status}}",
                                    }
                                ],
                            },
                        },
                    ],
                },
                {
                    "id": "target",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Target."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        clause = graph.nodes["router"].transitions[0].condition.equations[0]
        assert clause.right == "expected_status"

    def test_plain_values_unchanged(self):
        config = {
            "start_node_id": "router",
            "nodes": [
                {
                    "id": "router",
                    "type": "branch",
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "target",
                            "transition_condition": {
                                "type": "equation",
                                "equations": [
                                    {
                                        "left": "account_type",
                                        "operator": "==",
                                        "right": "premium",
                                    }
                                ],
                            },
                        },
                    ],
                },
                {
                    "id": "target",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Target."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        clause = graph.nodes["router"].transitions[0].condition.equations[0]
        assert clause.left == "account_type"
        assert clause.right == "premium"


class TestRetellImporterExtractDynamicVariables:
    """Tests for importing extract_dynamic_variables nodes."""

    def test_import_extract_node_preserves_variables(self, sample_retell_config_extract_variables):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_extract_variables)

        extract_node = graph.nodes["extract_dob"]
        assert len(extract_node.variables_to_extract) == 3
        assert extract_node.variables_to_extract[0].name == "dob_month"
        assert extract_node.variables_to_extract[0].description == (
            "The month of birth as a number 1-12. Convert month names to numbers "
            "(January=1, February=2, ... December=12). If no date was provided, use 0."
        )
        assert extract_node.variables_to_extract[0].type == "string"
        assert extract_node.variables_to_extract[0].choices == []

    def test_extract_node_retell_type_metadata(self, sample_retell_config_extract_variables):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_extract_variables)

        extract_node = graph.nodes["extract_dob"]
        assert extract_node.metadata["retell_type"] == "extract_dynamic_variables"

    def test_extract_node_has_equation_edges(self, sample_retell_config_extract_variables):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_extract_variables)

        extract_node = graph.nodes["extract_dob"]
        equation_transitions = [
            t for t in extract_node.transitions if t.condition.type == "equation"
        ]
        assert len(equation_transitions) == 1
        assert len(equation_transitions[0].condition.equations) == 3

    def test_extract_node_has_else_edge(self, sample_retell_config_extract_variables):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_extract_variables)

        extract_node = graph.nodes["extract_dob"]
        always_transitions = [t for t in extract_node.transitions if t.condition.type == "always"]
        assert len(always_transitions) == 1
        assert always_transitions[0].target_node_id == "dob_retry"

    def test_extract_node_is_extract_node(self, sample_retell_config_extract_variables):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_extract_variables)

        assert graph.nodes["extract_dob"].is_extract_node() is True
        assert graph.nodes["ask_dob"].is_extract_node() is False

    def test_full_graph_structure(self, sample_retell_config_extract_variables):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_extract_variables)

        assert len(graph.nodes) == 4
        assert graph.entry_node_id == "ask_dob"
        assert "extract_dob" in graph.nodes
        assert "dob_match" in graph.nodes
        assert "dob_retry" in graph.nodes


class TestRetellImporterOperatorField:
    """Tests for importing the operator field on equation transition conditions."""

    def test_and_operator_imported(self):
        config = {
            "start_node_id": "router",
            "nodes": [
                {
                    "id": "router",
                    "type": "branch",
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "target",
                            "transition_condition": {
                                "type": "equation",
                                "operator": "&&",
                                "equations": [
                                    {"left": "x", "operator": "==", "right": "1"},
                                    {"left": "y", "operator": "==", "right": "2"},
                                ],
                            },
                        },
                    ],
                },
                {
                    "id": "target",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Target."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        condition = graph.nodes["router"].transitions[0].condition
        assert condition.logical_operator == "and"

    def test_or_operator_imported(self):
        config = {
            "start_node_id": "router",
            "nodes": [
                {
                    "id": "router",
                    "type": "branch",
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "target",
                            "transition_condition": {
                                "type": "equation",
                                "operator": "||",
                                "equations": [
                                    {"left": "x", "operator": "==", "right": "1"},
                                    {"left": "y", "operator": "==", "right": "2"},
                                ],
                            },
                        },
                    ],
                },
                {
                    "id": "target",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Target."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        condition = graph.nodes["router"].transitions[0].condition
        assert condition.logical_operator == "or"

    def test_no_operator_defaults_to_and(self):
        config = {
            "start_node_id": "router",
            "nodes": [
                {
                    "id": "router",
                    "type": "branch",
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "target",
                            "transition_condition": {
                                "type": "equation",
                                "equations": [
                                    {"left": "x", "operator": "==", "right": "1"},
                                ],
                            },
                        },
                    ],
                },
                {
                    "id": "target",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Target."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        condition = graph.nodes["router"].transitions[0].condition
        assert condition.logical_operator == "and"


class TestRetellImporterAlwaysEdge:
    """Tests for importing always_edge on conversation nodes."""

    def test_always_edge_imported_as_always_transition(self):
        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Say goodbye."},
                    "edges": [],
                    "always_edge": {
                        "id": "always-edge-1",
                        "destination_node_id": "end",
                        "transition_condition": {
                            "type": "prompt",
                            "prompt": "Always",
                        },
                    },
                },
                {
                    "id": "end",
                    "type": "end",
                    "instruction": {"type": "prompt", "text": "End."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        main = graph.nodes["main"]
        assert len(main.transitions) == 1
        assert main.transitions[0].target_node_id == "end"
        assert main.transitions[0].condition.type == "always"

    def test_always_edge_appended_after_regular_edges(self):
        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Help."},
                    "edges": [
                        {
                            "id": "edge-1",
                            "destination_node_id": "branch",
                            "transition_condition": {
                                "type": "prompt",
                                "prompt": "User needs help",
                            },
                        },
                    ],
                    "always_edge": {
                        "id": "always-edge-1",
                        "destination_node_id": "end",
                        "transition_condition": {
                            "type": "prompt",
                            "prompt": "Always",
                        },
                    },
                },
                {
                    "id": "branch",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Branch."},
                    "edges": [],
                },
                {
                    "id": "end",
                    "type": "end",
                    "instruction": {"type": "prompt", "text": "End."},
                    "edges": [],
                },
            ],
        }
        importer = RetellImporter()
        graph = importer.import_agent(config)

        main = graph.nodes["main"]
        assert len(main.transitions) == 2
        assert main.transitions[0].condition.type == "llm_prompt"
        assert main.transitions[1].condition.type == "always"
        assert main.transitions[1].target_node_id == "end"

    def test_pharmacy_fixture_always_edge_imported(self):
        """The pharmacy refill agent uses always_edge on conversation nodes."""
        fixture_path = Path("test-data/template_pharmacy_refill_agent_cf.json")
        if not fixture_path.exists():
            pytest.skip("test-data/ fixtures not available (gitignored)")
        importer = RetellImporter()
        graph = importer.import_agent(fixture_path)

        patient_unavailable = graph.nodes["patient_unavailable"]
        assert len(patient_unavailable.transitions) == 1
        assert patient_unavailable.transitions[0].target_node_id == "synth_end_call"
        assert patient_unavailable.transitions[0].condition.type == "always"

        guardian_unavailable = graph.nodes["guardian_unavailable"]
        assert len(guardian_unavailable.transitions) == 1
        assert guardian_unavailable.transitions[0].target_node_id == "synth_end_call"
        assert guardian_unavailable.transitions[0].condition.type == "always"


class TestRetellImporterWrappedFormat:
    """Tests for importing Retell UI agent wrapper format."""

    def test_can_import_wrapped_format(self, sample_retell_config):
        wrapped = {
            "agent_id": "",
            "response_engine": {"type": "conversation-flow"},
            "conversationFlow": sample_retell_config,
        }
        importer = RetellImporter()
        assert importer.can_import(wrapped) is True

    def test_import_wrapped_format(self, sample_retell_config):
        wrapped = {
            "agent_id": "",
            "response_engine": {"type": "conversation-flow"},
            "conversationFlow": sample_retell_config,
        }
        importer = RetellImporter()
        graph = importer.import_agent(wrapped)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 4
