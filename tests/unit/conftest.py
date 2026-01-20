"""Pytest configuration and fixtures for voicetest unit tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def reset_di_container():
    """Reset the DI container before each test to ensure isolation."""
    from voicetest.container import reset_container

    reset_container()
    yield
    reset_container()


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


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
