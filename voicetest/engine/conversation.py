"""Conversation engine - single source of truth for turn processing.

This module provides ConversationEngine, used by BOTH the test runner AND live calls.
If tests pass, real calls behave the same.
"""

from dataclasses import dataclass
from dataclasses import field
import hashlib
import json
import logging
from typing import Any

import dspy

from voicetest.engine.equations import evaluate_equation
from voicetest.engine.modules import ConversationModule
from voicetest.engine.modules import StateModule
from voicetest.llm import OnTokenCallback
from voicetest.llm import _invoke_callback
from voicetest.llm import call_llm
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.results import Message
from voicetest.models.results import ToolCall
from voicetest.models.test_case import RunOptions
from voicetest.util.retry import OnErrorCallback
from voicetest.util.templating import expand_snippets
from voicetest.util.templating import substitute_variables


logger = logging.getLogger(__name__)


@dataclass
class TurnResult:
    """Result from processing a single turn."""

    response: str
    transitioned_to: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    end_call_invoked: bool = False


class ConversationEngine:
    """Turn processor shared by tests and live calls — single source of truth."""

    def __init__(
        self,
        graph: AgentGraph,
        model: str,
        options: RunOptions | None = None,
        dynamic_variables: dict | None = None,
    ):
        self.graph = graph
        self.model = model
        self.options = options or RunOptions()
        self._dynamic_variables = dynamic_variables or {}

        self._no_cache = self.options.no_cache if self.options else False
        self._module = ConversationModule(graph)
        self._on_turn = None

        self._current_node = graph.entry_node_id
        self._transcript: list[Message] = []
        self._nodes_visited: list[str] = [graph.entry_node_id]
        self._tools_called: list[ToolCall] = []
        self._end_call_invoked = False
        self._originator_stack: list[str] = []

    @property
    def current_node(self) -> str:
        """Current node ID."""
        return self._current_node

    @property
    def transcript(self) -> list[Message]:
        """Conversation transcript (copy)."""
        return self._transcript.copy()

    @property
    def nodes_visited(self) -> list[str]:
        """List of node IDs visited during conversation (copy)."""
        return self._nodes_visited.copy()

    @property
    def tools_called(self) -> list[ToolCall]:
        """List of tool calls made during conversation (copy)."""
        return self._tools_called.copy()

    @property
    def end_call_invoked(self) -> bool:
        """Whether end_call was invoked."""
        return self._end_call_invoked

    @property
    def originator_stack(self) -> list[str]:
        """Stack of originator node IDs for global node go-back (copy)."""
        return self._originator_stack.copy()

    @property
    def _current_originator(self) -> str | None:
        """The originator node ID at the top of the stack, or None."""
        return self._originator_stack[-1] if self._originator_stack else None

    async def _append_message(self, message: Message) -> None:
        """Append a message to the transcript and notify via callback."""
        self._transcript.append(message)
        if self._on_turn:
            await _invoke_callback(self._on_turn, self._transcript)

    async def add_user_message(self, content: str) -> None:
        """Add a user message to the transcript.

        Args:
            content: The user's message content.
        """
        await self._append_message(
            Message(
                role="user",
                content=content,
                metadata={"node_id": self._current_node},
            )
        )

    def _last_user_message(self) -> str:
        """Extract the most recent user message from the transcript."""
        for msg in reversed(self._transcript):
            if msg.role == "user":
                return msg.content
        return ""

    def _expand(self, text: str) -> str:
        """Expand snippet refs and substitute dynamic variables."""
        return substitute_variables(
            expand_snippets(text, self.graph.snippets),
            self._dynamic_variables,
        )

    async def advance(
        self,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Advance through silent nodes to a conversation node, then respond from it."""
        max_hops = 20
        accumulated_tool_calls: list[ToolCall] = []
        end_call_invoked = False
        has_advanced = False
        last_transition_target: str | None = None

        for _ in range(max_hops):
            node = self.graph.nodes[self._current_node]
            state_module = self._module.get_state_module(self._current_node)
            if state_module is None:
                raise ValueError(f"Unknown node: {self._current_node}")

            if node.is_extract_node():
                result = await self._evaluate_extract_node(node, state_module, on_error=on_error)
                accumulated_tool_calls.extend(result.tool_calls)
                if result.end_call_invoked:
                    end_call_invoked = True
                if result.transitioned_to is None:
                    break
                last_transition_target = result.transitioned_to
                has_advanced = True
                continue

            if node.is_logic_node():
                result = await self._evaluate_transitions(node)
                accumulated_tool_calls.extend(result.tool_calls)
                if result.transitioned_to is None:
                    break
                last_transition_target = result.transitioned_to
                has_advanced = True
                continue

            if node.is_function_node():
                result = await self._evaluate_function_node(node)
                accumulated_tool_calls.extend(result.tool_calls)
                if result.transitioned_to is None:
                    break
                last_transition_target = result.transitioned_to
                has_advanced = True
                continue

            if (node.is_end_node() or node.is_transfer_node()) and not node.state_prompt:
                self._end_call_invoked = True
                return TurnResult(
                    response="",
                    tool_calls=accumulated_tool_calls,
                    end_call_invoked=True,
                )

            if not has_advanced and self._last_user_message():
                result = await self._evaluate_transition(node, on_error=on_error)
                if result.transitioned_to:
                    accumulated_tool_calls.extend(result.tool_calls)
                    last_transition_target = result.transitioned_to
                    has_advanced = True
                    continue

            break

        result = await self._generate_response(on_token=on_token, on_error=on_error)
        result.tool_calls = accumulated_tool_calls + result.tool_calls
        if end_call_invoked:
            result.end_call_invoked = True
        if result.transitioned_to is None and last_transition_target is not None:
            result.transitioned_to = last_transition_target
        return result

    async def _process_node(
        self,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Process the current node once (single-node dispatch; advance() loops)."""
        node = self.graph.nodes[self._current_node]
        state_module = self._module.get_state_module(self._current_node)
        if state_module is None:
            raise ValueError(f"Unknown node: {self._current_node}")

        if node.is_extract_node():
            return await self._evaluate_extract_node(node, state_module, on_error=on_error)
        if node.is_logic_node():
            return await self._evaluate_transitions(node)
        if node.is_function_node():
            return await self._evaluate_function_node(node)
        if (node.is_end_node() or node.is_transfer_node()) and not node.state_prompt:
            self._end_call_invoked = True
            return TurnResult(response="", end_call_invoked=True)
        return await self._generate_response(on_token=on_token, on_error=on_error)

    async def _evaluate_transition(
        self,
        node: AgentNode,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Evaluate transitions out of a conversation node."""
        available_transitions = self._module.format_transitions(
            self._current_node, originator_id=self._current_originator
        )
        if not available_transitions:
            return TurnResult(response="")

        current_node_messages = [
            m
            for m in self._transcript
            if m.metadata.get("node_id") == self._current_node and m.role != "tool"
        ]
        conversation_history = self._format_transcript(current_node_messages)

        last_agent_message = "(agent has not spoken in this state yet)"
        for msg in reversed(current_node_messages):
            if msg.role == "assistant":
                last_agent_message = msg.content
                break

        state_module = self._module.get_state_module(self._current_node)
        state_prompt = node.state_prompt
        if state_module:
            state_prompt = self._expand(state_module.instructions)

        transition_result = await call_llm(
            self.model,
            self._module._transition_signature,
            on_error=on_error,
            no_cache=self._no_cache,
            predictor_class=dspy.ChainOfThought,
            current_state_prompt=state_prompt,
            conversation_history=conversation_history,
            last_agent_message=last_agent_message,
            available_transitions=available_transitions,
        )

        if not transition_result.objectives_complete:
            return TurnResult(response="")

        result = await self._evaluate_transitions(
            node, llm_decision=transition_result, apply_always_fallback=False
        )
        if result.transitioned_to:
            return result

        # Global-node entries and go-back targets aren't in `node.transitions`
        # — they're synthesized into `available_transitions` for the LLM only.
        # If the LLM picked one, fire it directly.
        target = transition_result.transition_to.strip().lower()
        if target and target != "none" and target in self.graph.nodes:
            await self._apply_transition(result, target)
        return result

    async def _generate_response(
        self,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Generate the agent's spoken response from the current node."""
        state_module = self._module.get_state_module(self._current_node)
        if state_module is None:
            raise ValueError(f"Unknown node: {self._current_node}")

        node = self.graph.nodes[self._current_node]
        user_message = self._last_user_message()

        general_instructions = self._expand(self._module.instructions)
        state_instructions = self._expand(state_module.instructions)

        conversation_history = self._format_transcript(self._transcript)
        response_sig = state_module.create_response_signature(state_instructions)

        response_kwargs = {
            "general_instructions": general_instructions,
            "conversation_history": conversation_history,
            "user_message": user_message,
        }

        # Fingerprint the available transitions into cache_salt so edits to
        # edges bust the response cache.
        cache_salt = None
        available_transitions = self._module.format_transitions(
            self._current_node, originator_id=self._current_originator
        )
        if available_transitions:
            cache_salt = hashlib.sha256(
                json.dumps([t.model_dump() for t in available_transitions], sort_keys=True).encode()
            ).hexdigest()[:16]

        result = await call_llm(
            self.model,
            response_sig,
            on_token=on_token,
            stream_field="response" if on_token else None,
            on_error=on_error,
            cache_salt=cache_salt,
            no_cache=self._no_cache,
            predictor_class=dspy.Predict,
            **response_kwargs,
        )

        turn_result = TurnResult(response=result.response)

        await self._append_message(
            Message(
                role="assistant",
                content=result.response,
                metadata={"node_id": self._current_node},
            )
        )

        # On conversation nodes, always-edges fire AFTER the agent speaks
        # (linear advance), not as a pre-response transition.
        always_target = self._find_always_transition(node)
        if always_target:
            await self._apply_transition(turn_result, always_target)

        if (node.is_end_node() or node.is_transfer_node()) and not turn_result.transitioned_to:
            turn_result.end_call_invoked = True
            self._end_call_invoked = True

        return turn_result

    async def _apply_transition(self, turn_result: TurnResult, target: str) -> None:
        """Record a transition; manages the originator stack for global nodes."""
        source_node = self.graph.nodes[self._current_node]
        target_node = self.graph.nodes.get(target)

        # Go-back: source is global and target matches the originator
        if (
            source_node.global_node_setting
            and self._originator_stack
            and self._originator_stack[-1] == target
        ):
            self._originator_stack.pop()
        elif target_node and target_node.global_node_setting:
            # Entering a global node: push current node as originator
            self._originator_stack.append(self._current_node)
        elif source_node.global_node_setting and self._originator_stack:
            # Leaving a global node forward via regular edge: pop originator
            self._originator_stack.pop()

        self._current_node = target
        self._nodes_visited.append(target)
        turn_result.transitioned_to = target
        tool_call = ToolCall(
            name=f"route_to_{target}",
            arguments={},
            result=target,
        )
        self._tools_called.append(tool_call)
        turn_result.tool_calls.append(tool_call)
        await self._append_message(
            Message(
                role="tool",
                content=f"Transitioned to {target}",
                metadata={"tool_name": f"route_to_{target}", "node_id": target},
            )
        )

    async def _evaluate_transitions(
        self,
        node: AgentNode,
        llm_decision: Any | None = None,
        apply_always_fallback: bool = True,
    ) -> TurnResult:
        """Centralized transition dispatcher; dispatches per `condition.type`."""
        turn_result = TurnResult(response="")
        fallback_target: str | None = None
        llm_target = ""
        if llm_decision is not None:
            llm_target = getattr(llm_decision, "transition_to", "").strip().lower()

        for transition in node.transitions:
            ctype = transition.condition.type
            if ctype == "always":
                if fallback_target is None:
                    fallback_target = transition.target_node_id
                continue
            if ctype == "tool_call":
                logger.warning(
                    "tool_call transition on node %s skipped; tool execution is "
                    "not supported (see voicetestdev/voicetest#51)",
                    node.id,
                )
                continue
            if ctype == "equation":
                if not transition.condition.equations:
                    continue
                combiner = all if transition.condition.logical_operator == "and" else any
                if combiner(
                    evaluate_equation(clause, self._dynamic_variables)
                    for clause in transition.condition.equations
                ):
                    await self._apply_transition(turn_result, transition.target_node_id)
                    return turn_result
                continue
            if ctype == "llm_prompt":
                if llm_target and llm_target == transition.target_node_id.lower():
                    await self._apply_transition(turn_result, transition.target_node_id)
                    return turn_result
                continue

        if apply_always_fallback and fallback_target:
            await self._apply_transition(turn_result, fallback_target)
        return turn_result

    async def _evaluate_function_node(self, node: AgentNode) -> TurnResult:
        """Pass through a function node without executing the tool (see #51)."""
        logger.warning(
            "function node %s reached; tool execution is not supported "
            "(see voicetestdev/voicetest#51)",
            node.id,
        )
        return await self._evaluate_transitions(node)

    async def _evaluate_extract_node(
        self,
        node: AgentNode,
        state_module: StateModule,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Extract variables via LLM, then route via the centralized dispatcher."""
        user_message = self._last_user_message()

        attrs: dict = {
            "__doc__": self._expand(state_module.instructions),
            "conversation_history": dspy.InputField(desc="Full conversation transcript"),
            "user_message": dspy.InputField(desc="Most recent user message"),
        }
        for var in node.variables_to_extract:
            desc = var.description
            if var.choices:
                desc += f" Must be one of: {var.choices}"
            if var.type != "string":
                desc += f" (type: {var.type})"
            attrs[var.name] = dspy.OutputField(desc=desc)

        sig = type("ExtractVariables", (dspy.Signature,), attrs)

        result = await call_llm(
            self.model,
            sig,
            on_error=on_error,
            no_cache=self._no_cache,
            predictor_class=dspy.Predict,
            conversation_history=self._format_transcript(self._transcript),
            user_message=user_message,
        )

        extracted = {}
        for var in node.variables_to_extract:
            value = getattr(result, var.name, None)
            if value is not None:
                self._dynamic_variables[var.name] = str(value)
                extracted[var.name] = str(value)

        if extracted:
            parts = [f"{k}={v}" for k, v in extracted.items()]
            await self._append_message(
                Message(
                    role="tool",
                    content=f"Extracted: {', '.join(parts)}",
                    metadata={
                        "tool_name": "extract_variables",
                        "node_id": self._current_node,
                        "extracted": extracted,
                    },
                )
            )

        return await self._evaluate_transitions(node)

    def _find_always_transition(self, node: AgentNode) -> str | None:
        """Find the target of an always-type transition on a conversation node."""
        for t in node.transitions:
            if t.condition.type == "always":
                return t.target_node_id
        return None

    def _format_transcript(self, transcript: list[Message]) -> str:
        """Format transcript for LLM input."""
        if not transcript:
            return "(conversation just started)"

        lines = []
        for msg in transcript:
            lines.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset the engine to initial state."""
        self._current_node = self.graph.entry_node_id
        self._transcript = []
        self._nodes_visited = [self.graph.entry_node_id]
        self._tools_called = []
        self._end_call_invoked = False
        self._originator_stack = []
