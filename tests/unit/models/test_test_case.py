"""Tests for voicetest.models.test_case module."""


class TestRunOptions:
    """Tests for RunOptions model."""

    def test_default_options(self):
        from voicetest.models.test_case import RunOptions

        options = RunOptions()
        assert options.max_turns == 20
        assert options.timeout_seconds == 60.0
        assert options.verbose is False
        assert options.agent_model == "openai/gpt-4o-mini"
        assert options.simulator_model == "openai/gpt-4o-mini"
        assert options.judge_model == "openai/gpt-4o-mini"

    def test_custom_options(self):
        from voicetest.models.test_case import RunOptions

        options = RunOptions(
            max_turns=10,
            timeout_seconds=120.0,
            verbose=True,
            agent_model="openai/gpt-4o",
            simulator_model="openai/gpt-4o-mini",
            judge_model="anthropic/claude-3-haiku-20240307",
        )
        assert options.max_turns == 10
        assert options.timeout_seconds == 120.0
        assert options.verbose is True
        assert options.agent_model == "openai/gpt-4o"
        assert options.simulator_model == "openai/gpt-4o-mini"
        assert options.judge_model == "anthropic/claude-3-haiku-20240307"


class TestTestCase:
    """Tests for TestCase model."""

    def test_create_basic_test_case(self):
        from voicetest.models.test_case import TestCase

        test = TestCase(
            id="test-001",
            name="Basic greeting test",
            user_prompt="## Identity\nYou are John.\n\n## Goal\nSay hello."
        )
        assert test.id == "test-001"
        assert test.name == "Basic greeting test"
        assert "John" in test.user_prompt
        assert test.metrics == []
        assert test.required_nodes is None
        assert test.forbidden_nodes is None
        assert test.max_turns == 20

    def test_create_full_test_case(self):
        from voicetest.models.test_case import TestCase

        test = TestCase(
            id="billing-test",
            name="Billing inquiry test",
            user_prompt="## Identity\nJane\n\n## Goal\nAsk about bill",
            metrics=[
                "Agent greeted customer",
                "Agent addressed billing concern"
            ],
            required_nodes=["greeting", "billing"],
            forbidden_nodes=["escalation"],
            function_mocks={"get_balance": 100.00},
            max_turns=15
        )
        assert len(test.metrics) == 2
        assert test.required_nodes == ["greeting", "billing"]
        assert test.forbidden_nodes == ["escalation"]
        assert test.function_mocks["get_balance"] == 100.00
        assert test.max_turns == 15

    def test_test_case_json_serialization(self):
        from voicetest.models.test_case import TestCase

        test = TestCase(
            id="test-1",
            name="Test",
            user_prompt="Prompt",
            metrics=["metric1", "metric2"]
        )

        json_str = test.model_dump_json()
        restored = TestCase.model_validate_json(json_str)
        assert restored.id == "test-1"
        assert restored.metrics == ["metric1", "metric2"]
