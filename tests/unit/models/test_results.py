"""Tests for voicetest.models.results module."""

from datetime import datetime


class TestMessage:
    """Tests for Message model."""

    def test_create_user_message(self):
        from voicetest.models.results import Message

        msg = Message(role="user", content="Hello, I need help.")
        assert msg.role == "user"
        assert msg.content == "Hello, I need help."
        assert msg.timestamp is None
        assert msg.metadata == {}

    def test_create_assistant_message_with_timestamp(self):
        from voicetest.models.results import Message

        now = datetime.now()
        msg = Message(role="assistant", content="How can I help?", timestamp=now)
        assert msg.role == "assistant"
        assert msg.timestamp == now

    def test_create_message_with_metadata(self):
        from voicetest.models.results import Message

        msg = Message(
            role="tool",
            content="Account balance: $100",
            metadata={"tool_name": "get_balance", "duration_ms": 150},
        )
        assert msg.role == "tool"
        assert msg.metadata["tool_name"] == "get_balance"


class TestToolCall:
    """Tests for ToolCall model."""

    def test_create_tool_call(self):
        from voicetest.models.results import ToolCall

        call = ToolCall(
            name="lookup_account",
            arguments={"account_id": "12345"},
            result="Account found: John Doe",
        )
        assert call.name == "lookup_account"
        assert call.arguments["account_id"] == "12345"
        assert call.result == "Account found: John Doe"

    def test_create_tool_call_without_result(self):
        from voicetest.models.results import ToolCall

        call = ToolCall(name="send_notification", arguments={"message": "Hello"})
        assert call.result is None


class TestMetricResult:
    """Tests for MetricResult model."""

    def test_create_passed_metric(self):
        from voicetest.models.results import MetricResult

        result = MetricResult(
            metric="Agent greeted the customer",
            passed=True,
            reasoning="The agent said 'Hello, how can I help you today?'",
            confidence=0.95,
        )
        assert result.metric == "Agent greeted the customer"
        assert result.passed is True
        assert "Hello" in result.reasoning
        assert result.confidence == 0.95

    def test_create_failed_metric(self):
        from voicetest.models.results import MetricResult

        result = MetricResult(
            metric="Agent resolved the issue",
            passed=False,
            reasoning="The conversation ended without resolution",
        )
        assert result.passed is False
        assert result.confidence is None


class TestTestResult:
    """Tests for TestResult model."""

    def test_create_passed_result(self):
        from voicetest.models.results import Message, MetricResult, TestResult

        result = TestResult(
            test_id="test-001",
            test_name="Greeting test",
            status="pass",
            transcript=[
                Message(role="user", content="Hi"),
                Message(role="assistant", content="Hello!"),
            ],
            metric_results=[
                MetricResult(metric="Greeted user", passed=True, reasoning="Said hello")
            ],
            nodes_visited=["greeting", "end"],
            turn_count=1,
            duration_ms=1500,
            end_reason="agent_ended",
        )
        assert result.status == "pass"
        assert len(result.transcript) == 2
        assert len(result.metric_results) == 1
        assert result.nodes_visited == ["greeting", "end"]
        assert result.error_message is None

    def test_create_error_result(self):
        from voicetest.models.results import TestResult

        result = TestResult(
            test_id="test-002",
            test_name="Failed test",
            status="error",
            duration_ms=100,
            error_message="Connection timeout",
        )
        assert result.status == "error"
        assert result.error_message == "Connection timeout"
        assert result.transcript == []

    def test_result_json_serialization(self):
        from voicetest.models.results import Message, TestResult

        result = TestResult(
            test_id="t1",
            test_name="Test",
            status="pass",
            transcript=[Message(role="user", content="Hi")],
            turn_count=1,
            duration_ms=100,
            end_reason="complete",
        )

        json_str = result.model_dump_json()
        restored = TestResult.model_validate_json(json_str)
        assert restored.test_id == "t1"
        assert len(restored.transcript) == 1


class TestTestRun:
    """Tests for TestRun model."""

    def test_create_test_run(self):
        from voicetest.models.results import TestResult, TestRun

        now = datetime.now()
        run = TestRun(
            run_id="run-001",
            started_at=now,
            results=[
                TestResult(
                    test_id="t1",
                    test_name="Test 1",
                    status="pass",
                    turn_count=1,
                    duration_ms=100,
                    end_reason="done",
                ),
                TestResult(
                    test_id="t2",
                    test_name="Test 2",
                    status="fail",
                    turn_count=2,
                    duration_ms=200,
                    end_reason="done",
                ),
                TestResult(
                    test_id="t3",
                    test_name="Test 3",
                    status="pass",
                    turn_count=1,
                    duration_ms=150,
                    end_reason="done",
                ),
            ],
        )
        assert run.run_id == "run-001"
        assert len(run.results) == 3

    def test_passed_count(self):
        from voicetest.models.results import TestResult, TestRun

        run = TestRun(
            run_id="run-002",
            started_at=datetime.now(),
            results=[
                TestResult(
                    test_id="t1",
                    test_name="T1",
                    status="pass",
                    turn_count=1,
                    duration_ms=100,
                    end_reason="done",
                ),
                TestResult(
                    test_id="t2",
                    test_name="T2",
                    status="fail",
                    turn_count=1,
                    duration_ms=100,
                    end_reason="done",
                ),
                TestResult(
                    test_id="t3",
                    test_name="T3",
                    status="pass",
                    turn_count=1,
                    duration_ms=100,
                    end_reason="done",
                ),
            ],
        )
        assert run.passed_count == 2

    def test_failed_count(self):
        from voicetest.models.results import TestResult, TestRun

        run = TestRun(
            run_id="run-003",
            started_at=datetime.now(),
            results=[
                TestResult(
                    test_id="t1",
                    test_name="T1",
                    status="pass",
                    turn_count=1,
                    duration_ms=100,
                    end_reason="done",
                ),
                TestResult(
                    test_id="t2",
                    test_name="T2",
                    status="fail",
                    turn_count=1,
                    duration_ms=100,
                    end_reason="done",
                ),
                TestResult(
                    test_id="t3",
                    test_name="T3",
                    status="error",
                    turn_count=1,
                    duration_ms=100,
                    end_reason="done",
                ),
            ],
        )
        assert run.failed_count == 1  # only "fail", not "error"

    def test_empty_run(self):
        from voicetest.models.results import TestRun

        run = TestRun(run_id="empty", started_at=datetime.now())
        assert run.passed_count == 0
        assert run.failed_count == 0
        assert run.completed_at is None
