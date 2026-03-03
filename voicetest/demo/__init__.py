"""Demo mode for voicetest.

Provides bundled demo agent and tests for trying voicetest without external files.
"""

from importlib import resources
import json
from typing import Any


def get_demo_agent() -> dict[str, Any]:
    """Load the bundled demo agent configuration.

    Returns:
        Dict containing the demo agent configuration (Retell LLM format).
    """
    demo_files = resources.files("voicetest.demo")
    agent_json = demo_files.joinpath("agent.json").read_text()
    return json.loads(agent_json)


def get_demo_tests() -> list[dict[str, Any]]:
    """Load the bundled demo test cases.

    Returns:
        List of test case dicts compatible with voicetest test format.
    """
    demo_files = resources.files("voicetest.demo")
    tests_json = demo_files.joinpath("tests.json").read_text()
    return json.loads(tests_json)


def get_showcase_agents() -> list[tuple[str, dict[str, Any]]]:
    """Load all bundled showcase agent configurations.

    Returns:
        List of (name, config) tuples for each showcase agent.
    """
    demo_files = resources.files("voicetest.demo")
    agents = [
        ("Acme Healthcare", "agent.json"),
        ("Skyline Travel", "travel-agent.json"),
        ("TechCorp IT Support", "helpdesk-agent.json"),
    ]
    result = []
    for name, filename in agents:
        config = json.loads(demo_files.joinpath(filename).read_text())
        result.append((name, config))
    return result
