"""Pytest configuration and fixtures for voicetest unit tests."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def reset_di_container():
    """Reset the DI container before each test to ensure isolation."""
    from voicetest.container import reset_container

    reset_container()
    yield
    reset_container()


@pytest.fixture
def db_client(tmp_path, monkeypatch):
    """Create a test client with isolated database."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

    from voicetest.rest import app
    from voicetest.rest import init_storage

    init_storage()

    return TestClient(app)


@pytest.fixture
def platform_client(tmp_path, monkeypatch):
    """Create a test client with isolated database, cleared API keys, and temp settings dir."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

    monkeypatch.delenv("RETELL_API_KEY", raising=False)
    monkeypatch.delenv("VAPI_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".voicetest").mkdir()

    from voicetest.rest import app
    from voicetest.rest import init_storage

    init_storage()

    return TestClient(app)


# fixtures_dir is inherited from tests/conftest.py


@pytest.fixture
def retell_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return path to Retell test fixtures."""
    return fixtures_dir / "retell"


@pytest.fixture
def sample_retell_config(retell_fixtures_dir: Path) -> dict:
    """Load sample Retell configuration."""
    config_path = retell_fixtures_dir / "sample_config.json"
    return json.loads(config_path.read_text())


@pytest.fixture
def sample_retell_config_path(retell_fixtures_dir: Path) -> Path:
    """Return path to sample Retell configuration file."""
    return retell_fixtures_dir / "sample_config.json"


@pytest.fixture
def sample_test_cases(retell_fixtures_dir: Path) -> list[dict]:
    """Load sample test cases."""
    tests_path = retell_fixtures_dir / "sample_tests.json"
    return json.loads(tests_path.read_text())


@pytest.fixture
def sample_retell_llm_config(retell_fixtures_dir: Path) -> dict:
    """Load sample Retell LLM configuration."""
    config_path = retell_fixtures_dir / "sample_llm_config.json"
    return json.loads(config_path.read_text())


@pytest.fixture
def sample_retell_llm_config_path(retell_fixtures_dir: Path) -> Path:
    """Return path to sample Retell LLM configuration file."""
    return retell_fixtures_dir / "sample_llm_config.json"


@pytest.fixture
def sample_retell_llm_dashboard_export(retell_fixtures_dir: Path) -> dict:
    """Load sample Retell LLM dashboard export (wrapped in retellLlmData)."""
    config_path = retell_fixtures_dir / "sample_llm_dashboard_export.json"
    return json.loads(config_path.read_text())


@pytest.fixture
def sample_retell_llm_dashboard_export_path(retell_fixtures_dir: Path) -> Path:
    """Return path to sample Retell LLM dashboard export file."""
    return retell_fixtures_dir / "sample_llm_dashboard_export.json"


@pytest.fixture
def sample_retell_config_complex(retell_fixtures_dir: Path) -> dict:
    """Load complex Retell Conversation Flow configuration with tools."""
    config_path = retell_fixtures_dir / "sample_config_complex.json"
    return json.loads(config_path.read_text())


@pytest.fixture
def sample_retell_config_complex_path(retell_fixtures_dir: Path) -> Path:
    """Return path to complex Retell configuration file."""
    return retell_fixtures_dir / "sample_config_complex.json"


@pytest.fixture
def vapi_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return path to VAPI test fixtures."""
    return fixtures_dir / "vapi"


@pytest.fixture
def sample_vapi_assistant(vapi_fixtures_dir: Path) -> dict:
    """Load sample VAPI assistant configuration."""
    config_path = vapi_fixtures_dir / "sample_assistant.json"
    return json.loads(config_path.read_text())


@pytest.fixture
def sample_vapi_assistant_path(vapi_fixtures_dir: Path) -> Path:
    """Return path to sample VAPI assistant file."""
    return vapi_fixtures_dir / "sample_assistant.json"


@pytest.fixture
def sample_vapi_assistant_simple(vapi_fixtures_dir: Path) -> dict:
    """Load simple VAPI assistant configuration."""
    config_path = vapi_fixtures_dir / "sample_assistant_simple.json"
    return json.loads(config_path.read_text())


@pytest.fixture
def sample_vapi_squad(vapi_fixtures_dir: Path) -> dict:
    """Load sample VAPI squad configuration."""
    config_path = vapi_fixtures_dir / "sample_squad.json"
    return json.loads(config_path.read_text())


@pytest.fixture
def sample_vapi_squad_path(vapi_fixtures_dir: Path) -> Path:
    """Return path to sample VAPI squad file."""
    return vapi_fixtures_dir / "sample_squad.json"


@pytest.fixture
def livekit_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return path to LiveKit test fixtures."""
    return fixtures_dir / "livekit"


@pytest.fixture
def sample_livekit_agent_path(livekit_fixtures_dir: Path) -> Path:
    """Return path to sample LiveKit agent Python file."""
    return livekit_fixtures_dir / "sample_agent.py"


@pytest.fixture
def sample_livekit_agent_code(sample_livekit_agent_path: Path) -> str:
    """Load sample LiveKit agent Python code."""
    return sample_livekit_agent_path.read_text()


@pytest.fixture
def sample_livekit_simple_path(livekit_fixtures_dir: Path) -> Path:
    """Return path to simple LiveKit agent file."""
    return livekit_fixtures_dir / "sample_agent_simple.py"


@pytest.fixture
def sample_livekit_simple_code(sample_livekit_simple_path: Path) -> str:
    """Load simple LiveKit agent Python code."""
    return sample_livekit_simple_path.read_text()


# Common AgentGraph fixtures for testing


@pytest.fixture
def simple_graph():
    """Simple two-node graph with greeting and farewell nodes."""
    from voicetest.models.agent import AgentGraph
    from voicetest.models.agent import AgentNode
    from voicetest.models.agent import Transition
    from voicetest.models.agent import TransitionCondition

    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user warmly.",
                transitions=[
                    Transition(
                        target_node_id="farewell",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User wants to leave"
                        ),
                    )
                ],
            ),
            "farewell": AgentNode(
                id="farewell",
                state_prompt="Say goodbye politely.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


@pytest.fixture
def single_node_graph():
    """Single-node graph for basic testing."""
    from voicetest.models.agent import AgentGraph
    from voicetest.models.agent import AgentNode

    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="You are a helpful assistant.",
                transitions=[],
            ),
        },
        entry_node_id="main",
        source_type="custom",
    )


@pytest.fixture
def graph_with_tools():
    """Graph with tools attached to nodes."""
    from voicetest.models.agent import AgentGraph
    from voicetest.models.agent import AgentNode
    from voicetest.models.agent import ToolDefinition
    from voicetest.models.agent import Transition
    from voicetest.models.agent import TransitionCondition

    lookup_tool = ToolDefinition(
        name="lookup_user",
        description="Look up user in database",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID"},
            },
            "required": ["user_id"],
        },
    )
    end_call_tool = ToolDefinition(
        name="end_call",
        description="End the call",
        parameters={},
    )

    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user.",
                tools=[end_call_tool],
                transitions=[
                    Transition(
                        target_node_id="lookup",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User wants to check their account"
                        ),
                    )
                ],
            ),
            "lookup": AgentNode(
                id="lookup",
                state_prompt="Look up the user's account.",
                tools=[lookup_tool, end_call_tool],
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


@pytest.fixture
def multi_node_graph():
    """Multi-node graph with branching transitions."""
    from voicetest.models.agent import AgentGraph
    from voicetest.models.agent import AgentNode
    from voicetest.models.agent import Transition
    from voicetest.models.agent import TransitionCondition

    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the customer warmly and ask how you can help.",
                transitions=[
                    Transition(
                        target_node_id="billing",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User has billing question"
                        ),
                    ),
                    Transition(
                        target_node_id="support",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User needs technical support"
                        ),
                    ),
                ],
            ),
            "billing": AgentNode(
                id="billing",
                state_prompt="Help the customer with billing inquiries.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Billing resolved"),
                    )
                ],
            ),
            "support": AgentNode(
                id="support",
                state_prompt="Provide technical support.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Support complete"),
                    )
                ],
            ),
            "end": AgentNode(
                id="end",
                state_prompt="Thank the customer and end the call politely.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


@pytest.fixture
def graph_with_metadata():
    """Graph with source metadata set."""
    from voicetest.models.agent import AgentGraph
    from voicetest.models.agent import AgentNode

    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="You are a helpful assistant.",
                transitions=[],
            ),
        },
        entry_node_id="main",
        source_type="retell",
        source_metadata={
            "general_prompt": "You are a professional assistant.",
            "llm_id": "llm_test123",
            "model": "gpt-4o",
        },
    )


@pytest.fixture
def graph_with_dynamic_variables(fixtures_dir: Path):
    """Graph with {{variable}} placeholders in prompts."""
    from voicetest.models.agent import AgentGraph

    config_path = fixtures_dir / "graphs" / "graph_with_dynamic_variables.json"
    return AgentGraph.model_validate_json(config_path.read_text())


@pytest.fixture
def graph_dry_analysis(fixtures_dir: Path):
    """Graph with repeated and similar prompts for DRY analysis testing."""
    from voicetest.models.agent import AgentGraph

    config_path = fixtures_dir / "graphs" / "graph_dry_analysis.json"
    return AgentGraph.model_validate_json(config_path.read_text())
