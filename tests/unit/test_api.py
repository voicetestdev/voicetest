"""Tests for model precedence logic in run_test."""

import pytest

from voicetest.api import run_test
from voicetest.models.agent import AgentGraph, AgentNode, Transition, TransitionCondition
from voicetest.models.test_case import RunOptions, TestCase
from voicetest.settings import DEFAULT_MODEL


@pytest.fixture
def simple_graph() -> AgentGraph:
    """Create a simple agent graph for testing."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                instructions="Greet the user.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="done"),
                    )
                ],
            ),
            "end": AgentNode(id="end", instructions="End conversation.", transitions=[]),
        },
        entry_node_id="greeting",
        source_type="test",
    )


@pytest.fixture
def simple_test_case() -> TestCase:
    """Create a simple test case for testing."""
    return TestCase(
        name="test1",
        user_prompt="Test the agent.",
        metrics=["responds politely"],
    )


class TestAgentModelPrecedence:
    """Tests for agent model resolution with graph.default_model."""

    @pytest.mark.asyncio
    async def test_no_global_no_agent_default_uses_system_default(
        self, simple_graph, simple_test_case
    ):
        """When neither global nor agent default is set, use DEFAULT_MODEL."""
        options = RunOptions()  # agent_model = None

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == DEFAULT_MODEL

    @pytest.mark.asyncio
    async def test_no_global_with_agent_default_uses_agent_default(
        self, simple_graph, simple_test_case
    ):
        """When global not set but agent has default, use agent's default."""
        simple_graph.default_model = "openai/gpt-4o"
        options = RunOptions()  # agent_model = None

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == "openai/gpt-4o"
        assert len(result.model_overrides) >= 1
        agent_override = next((o for o in result.model_overrides if o.role == "agent"), None)
        assert agent_override is not None
        assert agent_override.actual == "openai/gpt-4o"
        assert "agent.default_model used" in agent_override.reason

    @pytest.mark.asyncio
    async def test_global_set_overrides_agent_default(self, simple_graph, simple_test_case):
        """When global is explicitly set, it wins over agent default."""
        simple_graph.default_model = "openai/gpt-4o"
        options = RunOptions(agent_model="anthropic/claude-3-sonnet")

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == "anthropic/claude-3-sonnet"
        agent_override = next((o for o in result.model_overrides if o.role == "agent"), None)
        assert agent_override is not None
        assert agent_override.actual == "anthropic/claude-3-sonnet"
        assert "global settings override" in agent_override.reason

    @pytest.mark.asyncio
    async def test_toggle_enabled_agent_default_wins_over_global(
        self, simple_graph, simple_test_case
    ):
        """When toggle enabled, agent default wins even over explicit global."""
        simple_graph.default_model = "openai/gpt-4o"
        options = RunOptions(agent_model="anthropic/claude-3-sonnet", test_model_precedence=True)

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == "openai/gpt-4o"
        agent_override = next((o for o in result.model_overrides if o.role == "agent"), None)
        assert agent_override is not None
        assert agent_override.actual == "openai/gpt-4o"
        assert "test_model_precedence enabled" in agent_override.reason

    @pytest.mark.asyncio
    async def test_global_matches_agent_default_no_override(self, simple_graph, simple_test_case):
        """When global equals agent default, no override is logged."""
        simple_graph.default_model = "openai/gpt-4o"
        options = RunOptions(agent_model="openai/gpt-4o")

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == "openai/gpt-4o"
        agent_override = next((o for o in result.model_overrides if o.role == "agent"), None)
        assert agent_override is None


class TestSimulatorModelPrecedence:
    """Tests for simulator model resolution with test_case.llm_model."""

    @pytest.mark.asyncio
    async def test_no_global_no_test_model_uses_system_default(
        self, simple_graph, simple_test_case
    ):
        """When neither global nor test model is set, use DEFAULT_MODEL."""
        options = RunOptions()  # simulator_model = None

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.simulator == DEFAULT_MODEL

    @pytest.mark.asyncio
    async def test_no_global_with_test_model_uses_test_model(self, simple_graph, simple_test_case):
        """When global not set but test has llm_model, use test's model."""
        simple_test_case.llm_model = "openai/gpt-4o-mini"
        options = RunOptions()  # simulator_model = None

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.simulator == "openai/gpt-4o-mini"
        sim_override = next((o for o in result.model_overrides if o.role == "simulator"), None)
        assert sim_override is not None
        assert sim_override.actual == "openai/gpt-4o-mini"
        assert "test_case.llm_model used" in sim_override.reason

    @pytest.mark.asyncio
    async def test_global_set_overrides_test_model(self, simple_graph, simple_test_case):
        """When global is explicitly set, it wins over test model."""
        simple_test_case.llm_model = "openai/gpt-4o-mini"
        options = RunOptions(simulator_model="anthropic/claude-3-haiku")

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.simulator == "anthropic/claude-3-haiku"
        sim_override = next((o for o in result.model_overrides if o.role == "simulator"), None)
        assert sim_override is not None
        assert sim_override.actual == "anthropic/claude-3-haiku"
        assert "global settings override" in sim_override.reason

    @pytest.mark.asyncio
    async def test_toggle_enabled_test_model_wins_over_global(self, simple_graph, simple_test_case):
        """When toggle enabled, test model wins even over explicit global."""
        simple_test_case.llm_model = "openai/gpt-4o-mini"
        options = RunOptions(simulator_model="anthropic/claude-3-haiku", test_model_precedence=True)

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.simulator == "openai/gpt-4o-mini"
        sim_override = next((o for o in result.model_overrides if o.role == "simulator"), None)
        assert sim_override is not None
        assert sim_override.actual == "openai/gpt-4o-mini"
        assert "test_model_precedence enabled" in sim_override.reason

    @pytest.mark.asyncio
    async def test_global_matches_test_model_no_override(self, simple_graph, simple_test_case):
        """When global equals test model, no override is logged."""
        simple_test_case.llm_model = "openai/gpt-4o-mini"
        options = RunOptions(simulator_model="openai/gpt-4o-mini")

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.simulator == "openai/gpt-4o-mini"
        sim_override = next((o for o in result.model_overrides if o.role == "simulator"), None)
        assert sim_override is None


class TestJudgeModel:
    """Tests for judge model resolution."""

    @pytest.mark.asyncio
    async def test_no_global_uses_system_default(self, simple_graph, simple_test_case):
        """When global judge not set, use DEFAULT_MODEL."""
        options = RunOptions()  # judge_model = None

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.judge == DEFAULT_MODEL

    @pytest.mark.asyncio
    async def test_global_set_uses_global(self, simple_graph, simple_test_case):
        """When global judge is set, use it."""
        options = RunOptions(judge_model="anthropic/claude-3-opus")

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.judge == "anthropic/claude-3-opus"


class TestCombinedPrecedence:
    """Tests for combined agent and simulator model precedence."""

    @pytest.mark.asyncio
    async def test_all_models_from_defaults_when_none_configured(
        self, simple_graph, simple_test_case
    ):
        """When nothing configured, all models use DEFAULT_MODEL."""
        options = RunOptions()

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == DEFAULT_MODEL
        assert result.models_used.simulator == DEFAULT_MODEL
        assert result.models_used.judge == DEFAULT_MODEL

    @pytest.mark.asyncio
    async def test_agent_and_test_models_both_override_when_global_not_set(
        self, simple_graph, simple_test_case
    ):
        """Agent default_model and test llm_model both apply when globals not set."""
        simple_graph.default_model = "openai/gpt-4o"
        simple_test_case.llm_model = "openai/gpt-4o-mini"
        options = RunOptions()

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == "openai/gpt-4o"
        assert result.models_used.simulator == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_global_overrides_both_agent_and_test_models(
        self, simple_graph, simple_test_case
    ):
        """Global settings override both agent default and test llm_model."""
        simple_graph.default_model = "openai/gpt-4o"
        simple_test_case.llm_model = "openai/gpt-4o-mini"
        options = RunOptions(
            agent_model="anthropic/claude-3-sonnet",
            simulator_model="anthropic/claude-3-haiku",
        )

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == "anthropic/claude-3-sonnet"
        assert result.models_used.simulator == "anthropic/claude-3-haiku"

    @pytest.mark.asyncio
    async def test_toggle_makes_agent_and_test_models_win_over_global(
        self, simple_graph, simple_test_case
    ):
        """Toggle enabled makes both agent default and test model win."""
        simple_graph.default_model = "openai/gpt-4o"
        simple_test_case.llm_model = "openai/gpt-4o-mini"
        options = RunOptions(
            agent_model="anthropic/claude-3-sonnet",
            simulator_model="anthropic/claude-3-haiku",
            test_model_precedence=True,
        )

        result = await run_test(simple_graph, simple_test_case, options, _mock_mode=True)

        assert result.models_used.agent == "openai/gpt-4o"
        assert result.models_used.simulator == "openai/gpt-4o-mini"
