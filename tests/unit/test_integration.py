"""Integration tests for the complete voicetest flow."""

from unittest.mock import patch

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import NodeType
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.agent import VariableExtraction
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.results import TestResult
from voicetest.models.results import TestRun
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.services.agents import AgentService
from voicetest.services.evaluation import EvaluationService
from voicetest.services.testing.execution import TestExecutionService
from voicetest.simulator.user_sim import SimulatorResponse
from voicetest.simulator.user_sim import UserSimulator


@pytest.fixture
def simple_agent_graph() -> AgentGraph:
    """Create a simple agent graph for testing."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the customer warmly and ask how you can help.",
                transitions=[
                    Transition(
                        target_node_id="help",
                        condition=TransitionCondition(
                            type="llm_prompt", value="Customer states their problem"
                        ),
                    )
                ],
                node_type=NodeType.CONVERSATION,
            ),
            "help": AgentNode(
                id="help",
                state_prompt="Help the customer with their request.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(
                            type="llm_prompt", value="Customer is satisfied"
                        ),
                    )
                ],
                node_type=NodeType.CONVERSATION,
            ),
            "end": AgentNode(
                id="end",
                state_prompt="Thank the customer and end the call politely.",
                transitions=[],
                node_type=NodeType.CONVERSATION,
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


@pytest.fixture
def simple_test_case() -> TestCase:
    """Create a simple test case."""
    return TestCase(
        name="Greeting test",
        user_prompt="When asked for name, say Test User. Say hello and see how the agent responds.",
        metrics=["Agent greeted the user."],
    )


class TestEndToEndFlow:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_import_retell_config(self, sample_retell_config, container):
        graph = await container.resolve(AgentService).import_agent(sample_retell_config)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 4

    @pytest.mark.asyncio
    async def test_run_test_returns_result(self, simple_agent_graph, simple_test_case, container):
        options = RunOptions(max_turns=2)

        result = await container.resolve(TestExecutionService).run_test(
            simple_agent_graph, simple_test_case, options=options, _mock_mode=True
        )

        assert isinstance(result, TestResult)
        assert result.test_id == "Greeting test"
        assert result.status in ("pass", "fail", "error")

    @pytest.mark.asyncio
    async def test_run_tests_returns_run(self, simple_agent_graph, container):
        test_cases = [
            TestCase(
                name="Test 1",
                user_prompt="When asked, say John. Say hello.",
            ),
            TestCase(
                name="Test 2",
                user_prompt="When asked, say Jane. Say goodbye.",
            ),
        ]

        result = await container.resolve(TestExecutionService).run_tests(
            simple_agent_graph, test_cases, options=RunOptions(max_turns=2), _mock_mode=True
        )

        assert isinstance(result, TestRun)
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_evaluate_transcript_returns_results(self, container):
        transcript = [
            Message(role="assistant", content="Hello! How can I help you?"),
            Message(role="user", content="I need help with my bill"),
            Message(role="assistant", content="I'd be happy to help with your billing question."),
        ]

        results = await container.resolve(EvaluationService).evaluate_transcript(
            transcript,
            metrics=["Agent greeted the user", "Agent acknowledged the request"],
            _mock_mode=True,
        )

        assert len(results) == 2
        assert all(isinstance(r, MetricResult) for r in results)


class TestRunTestBehavior:
    """Tests for run_test behavior."""

    @pytest.mark.asyncio
    async def test_run_test_tracks_nodes(self, simple_agent_graph, simple_test_case, container):
        result = await container.resolve(TestExecutionService).run_test(
            simple_agent_graph, simple_test_case, options=RunOptions(max_turns=3), _mock_mode=True
        )

        assert "greeting" in result.nodes_visited

    @pytest.mark.asyncio
    async def test_run_test_evaluates_metrics(
        self, simple_agent_graph, simple_test_case, container
    ):
        result = await container.resolve(TestExecutionService).run_test(
            simple_agent_graph, simple_test_case, options=RunOptions(max_turns=3), _mock_mode=True
        )

        assert len(result.metric_results) == len(simple_test_case.metrics)


class TestDynamicVariableRendering:
    @pytest.fixture
    def color_graph(self) -> AgentGraph:
        return AgentGraph(
            nodes={
                "offer": AgentNode(
                    id="offer",
                    state_prompt="Offer {{available_color}}. Previous pick: {{selected_color}}.",
                    transitions=[
                        Transition(
                            target_node_id="extract",
                            condition=TransitionCondition(type="always", value="Else"),
                        )
                    ],
                    node_type=NodeType.CONVERSATION,
                ),
                "extract": AgentNode(
                    id="extract",
                    state_prompt="",
                    variables_to_extract=[
                        VariableExtraction(
                            name="selected_color",
                            description=(
                                "If the caller accepts the suggested color, "
                                "return the value from {{available_color}}."
                            ),
                        )
                    ],
                    transitions=[
                        Transition(
                            target_node_id="confirm",
                            condition=TransitionCondition(type="always", value="Else"),
                        )
                    ],
                    node_type=NodeType.EXTRACT,
                ),
                "confirm": AgentNode(
                    id="confirm",
                    state_prompt="Confirm {{selected_color}} with the caller.",
                    node_type=NodeType.CONVERSATION,
                ),
            },
            entry_node_id="offer",
            source_type="custom",
            source_metadata={"start_speaker": "agent"},
        )

    @pytest.mark.asyncio
    async def test_repeated_runs_render_prompts_without_leaking_variables(
        self, color_graph, container
    ):
        test_case = TestCase(
            name="Color",
            user_prompt="Accept the suggested color.",
            type="rule",
            includes=["blue"],
            dynamic_variables={"available_color": "blue"},
        )
        runs: list[list] = []

        async def fake_call_llm(model, signature, **kwargs):
            runs[-1].append(signature)

            class Result:
                selected_color = "blue"
                response = "Great, blue it is."
                objectives_complete = False
                transition_to = "none"

            return Result()

        async def fake_generate(self, transcript, **kwargs):
            if any(m.role == "user" for m in transcript):
                return None
            return SimulatorResponse(message="Yes, use it.")

        service = container.resolve(TestExecutionService)
        with (
            patch("voicetest.engine.conversation.call_llm", side_effect=fake_call_llm),
            patch.object(UserSimulator, "generate", fake_generate),
        ):
            for _ in range(2):
                runs.append([])
                result = await service.run_test(
                    color_graph, test_case, options=RunOptions(max_turns=3)
                )
                assert result.status == "pass", result.error_message

        assert test_case.dynamic_variables == {"available_color": "blue"}
        for signatures in runs:
            docs = [sig.__doc__ for sig in signatures]
            assert "Offer blue. Previous pick: {{selected_color}}." in docs
            assert "Confirm blue with the caller." in docs
            extract_sig = next(sig for sig in signatures if sig.__name__ == "ExtractVariables")
            desc = extract_sig.output_fields["selected_color"].json_schema_extra["desc"]
            assert desc == "If the caller accepts the suggested color, return the value from blue."


class TestExportAgent:
    """Tests for export_agent function."""

    @pytest.mark.asyncio
    async def test_export_mermaid(self, simple_agent_graph, container):
        result = await container.resolve(AgentService).export_agent(
            simple_agent_graph, format="mermaid"
        )

        assert "flowchart" in result.lower()
        assert "greeting" in result
        assert "help" in result
        assert "end" in result

    @pytest.mark.asyncio
    async def test_export_livekit(self, simple_agent_graph, container):
        result = await container.resolve(AgentService).export_agent(
            simple_agent_graph, format="livekit"
        )

        assert "class Agent_greeting" in result
        assert "def __init__" in result
