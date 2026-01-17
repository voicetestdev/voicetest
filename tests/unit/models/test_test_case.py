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
    """Tests for TestCase model matching Retell export format."""

    def test_create_basic_test_case(self):
        from voicetest.models.test_case import TestCase

        test = TestCase(
            name="Basic greeting test",
            user_prompt="When asked for name, say John. Your goal is to say hello.",
        )
        assert test.name == "Basic greeting test"
        assert "John" in test.user_prompt
        assert test.metrics == []
        assert test.dynamic_variables == {}
        assert test.tool_mocks == []
        assert test.type == "simulation"
        assert test.llm_model is None

    def test_create_full_test_case(self):
        from voicetest.models.test_case import TestCase

        test = TestCase(
            name="Billing inquiry test",
            user_prompt="When asked for name, say Jane. Ask about your bill.",
            metrics=["Agent greeted customer and addressed billing concern."],
            dynamic_variables={"account_id": "12345"},
            tool_mocks=[],
            type="simulation",
            llm_model="gpt-4o-mini",
            creation_timestamp=1761074675536,
            user_modified_timestamp=1761074796123,
        )
        assert len(test.metrics) == 1
        assert test.metrics[0] == "Agent greeted customer and addressed billing concern."
        assert test.dynamic_variables == {"account_id": "12345"}
        assert test.tool_mocks == []
        assert test.llm_model == "gpt-4o-mini"
        assert test.creation_timestamp == 1761074675536

    def test_test_case_json_serialization(self):
        from voicetest.models.test_case import TestCase

        test = TestCase(name="Test", user_prompt="Prompt", metrics=["Criteria for success."])

        json_str = test.model_dump_json()
        restored = TestCase.model_validate_json(json_str)
        assert restored.name == "Test"
        assert restored.metrics == ["Criteria for success."]

    def test_retell_export_format_compatibility(self):
        """Verify compatibility with actual Retell export format."""
        from voicetest.models.test_case import TestCase

        retell_export = {
            "name": "Refill Declined wants 6 week callback",
            "dynamic_variables": {"customer_id": "cust_123"},
            "metrics": [
                "Confirms identity and DOB, acknowledges refill decline, "
                "asks why they declined, asks if they want callback in a month, "
                "confirms will do callback in 6 weeks, thanks caller, ends call."
            ],
            "user_prompt": "When asked for name or to confirm, provide or confirm "
            "you are Robert Wilson. When asked for DOB, provide September 17th 1983.",
            "creation_timestamp": 1761074675536,
            "user_modified_timestamp": 1761074796123,
            "type": "simulation",
            "tool_mocks": [],
            "llm_model": "gpt-4o-mini",
        }

        test = TestCase.model_validate(retell_export)
        assert test.name == "Refill Declined wants 6 week callback"
        assert test.dynamic_variables == {"customer_id": "cust_123"}
        assert len(test.metrics) == 1
        assert test.type == "simulation"
