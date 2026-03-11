"""Conversation engine - single source of truth for turn processing.

This module provides ConversationEngine, used by BOTH the test runner AND live calls.
If tests pass, real calls behave the same.
"""

from dataclasses import dataclass
from dataclasses import field
import hashlib
import json

import dspy

from voicetest.engine.equations import evaluate_equation
from voicetest.engine.modules import ConversationModule
from voicetest.engine.modules import StateModule
from voicetest.llm import OnTokenCallback
from voicetest.llm import call_llm
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.results import Message
from voicetest.models.results import ToolCall
from voicetest.models.test_case import RunOptions
from voicetest.retry import OnErrorCallback
from voicetest.templating import expand_snippets
from voicetest.templating import substitute_variables


@dataclass
class TurnResult:
    """Result from processing a single turn."""

    response: str
    transitioned_to: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    end_call_invoked: bool = False


class ConversationEngine:
    """THE source of truth for turn processing. Used by tests AND live calls.

    This class encapsulates:
    - Graph structure and configuration
    - Turn-by-turn message processing
    - State tracking (current node, transcript, nodes visited)
    - Transition detection and handling
    """

    def __init__(
        self,
        graph: AgentGraph,
        model: str,
        options: RunOptions | None = None,
        dynamic_variables: dict | None = None,
    ):
        """Initialize the conversation engine.

        Args:
            graph: The agent graph defining conversation flow.
            model: LLM model identifier (e.g., "openai/gpt-4o-mini").
            options: Run options for configuration.
            dynamic_variables: Variables for template substitution.
        """
        self.graph = graph
        self.model = model
        self.options = options or RunOptions()
        self._dynamic_variables = dynamic_variables or {}

        self._no_cache = self.options.no_cache if self.options else False
        self._module = ConversationModule(graph)

        # State
        self._current_node = graph.entry_node_id
        self._transcript: list[Message] = []
        self._nodes_visited: list[str] = [graph.entry_node_id]
        self._tools_called: list[ToolCall] = []
        self._end_call_invoked = False

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

    def add_user_message(self, content: str) -> None:
        """Add a user message to the transcript.

        Args:
            content: The user's message content.
        """
        self._transcript.append(
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

    async def advance(
        self,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Advance to a conversational node, then respond from it.

        Phase 1 — Advance: evaluate transitions from the current node,
        traverse silent nodes (logic, extract), until we land on a
        conversation node to respond from.

        Phase 2 — Respond: generate the agent's response from the
        landing node.
        """
        max_hops = 20
        accumulated_tool_calls: list[ToolCall] = []
        end_call_invoked = False
        has_advanced = False
        last_transition_target: str | None = None

        # Phase 1: advance to the conversation node we'll respond from.
        for _ in range(max_hops):
            node = self.graph.nodes[self._current_node]
            state_module = self._module.get_state_module(self._current_node)
            if state_module is None:
                raise ValueError(f"Unknown node: {self._current_node}")

            # Silent nodes: always process and continue advancing.
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
                result = self._evaluate_logic_node(state_module)
                accumulated_tool_calls.extend(result.tool_calls)
                if result.transitioned_to is None:
                    break
                last_transition_target = result.transitioned_to
                has_advanced = True
                continue

            # End/transfer nodes without a prompt: end immediately.
            if (node.is_end_node() or node.is_transfer_node()) and not node.state_prompt:
                self._end_call_invoked = True
                return TurnResult(
                    response="",
                    tool_calls=accumulated_tool_calls,
                    end_call_invoked=True,
                )

            # Conversation node (or end/transfer with prompt).
            # If we haven't advanced yet this turn and the user has spoken,
            # evaluate whether to advance past this node before responding.
            if not has_advanced and self._last_user_message():
                target = await self._evaluate_transition(node, on_error=on_error)
                if target:
                    turn_result = TurnResult(response="")
                    self._apply_transition(turn_result, target)
                    accumulated_tool_calls.extend(turn_result.tool_calls)
                    last_transition_target = target
                    has_advanced = True
                    continue

            # This is the node we respond from.
            break

        # Phase 2: generate response from the current conversation node.
        result = await self._generate_response(on_token=on_token, on_error=on_error)
        result.tool_calls = accumulated_tool_calls + result.tool_calls
        if end_call_invoked:
            result.end_call_invoked = True
        # Reflect the final node the engine settled on.
        if result.transitioned_to is None and last_transition_target is not None:
            result.transitioned_to = last_transition_target
        return result

    async def _process_node(
        self,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Process the current node once (single-node dispatch).

        Routes to the appropriate handler based on node type.
        Unlike advance(), this does not loop through multiple nodes.
        """
        node = self.graph.nodes[self._current_node]
        state_module = self._module.get_state_module(self._current_node)
        if state_module is None:
            raise ValueError(f"Unknown node: {self._current_node}")

        if node.is_extract_node():
            return await self._evaluate_extract_node(node, state_module, on_error=on_error)
        if node.is_logic_node():
            return self._evaluate_logic_node(state_module)
        if (node.is_end_node() or node.is_transfer_node()) and not node.state_prompt:
            self._end_call_invoked = True
            return TurnResult(response="", end_call_invoked=True)
        return await self._generate_response(on_token=on_token, on_error=on_error)

    async def _evaluate_transition(
        self,
        node: AgentNode,
        on_error: OnErrorCallback | None = None,
    ) -> str | None:
        """Evaluate LLM-prompted transitions from a conversation node.

        Returns the target node ID if a transition should fire, or None
        to stay in the current node. Always-edges are not evaluated here;
        they fire after the response in _generate_response.
        """
        available_transitions = self._module.format_transitions(self._current_node)
        if not available_transitions:
            return None

        # Scope history to messages within the current node only.
        current_node_messages = [
            m
            for m in self._transcript
            if m.metadata.get("node_id") == self._current_node and m.role != "tool"
        ]
        conversation_history = self._format_transcript(current_node_messages)

        # Expand the current node's state prompt for context.
        state_module = self._module.get_state_module(self._current_node)
        state_prompt = node.state_prompt
        if state_module:
            state_prompt = expand_snippets(state_module.instructions, self.graph.snippets)
            state_prompt = substitute_variables(state_prompt, self._dynamic_variables)

        transition_result = await call_llm(
            self.model,
            self._module._transition_signature,
            on_error=on_error,
            no_cache=self._no_cache,
            predictor_class=dspy.ChainOfThought,
            current_state_prompt=state_prompt,
            conversation_history=conversation_history,
            available_transitions=available_transitions,
        )
        target = transition_result.transition_to.strip().lower()

        if target and target != "none" and target in self.graph.nodes:
            return target
        return None

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

        # Expand static snippets first, then dynamic variables
        general_instructions = expand_snippets(self._module.instructions, self.graph.snippets)
        state_instructions = expand_snippets(state_module.instructions, self.graph.snippets)
        general_instructions = substitute_variables(general_instructions, self._dynamic_variables)
        state_instructions = substitute_variables(state_instructions, self._dynamic_variables)

        conversation_history = self._format_transcript(self._transcript)

        # Build response signature with expanded state prompt as docstring
        response_sig = state_module.create_response_signature(state_instructions)

        response_kwargs = {
            "general_instructions": general_instructions,
            "conversation_history": conversation_history,
            "user_message": user_message,
        }

        # Inject a fingerprint via cache_salt to bust cache when edges change.
        cache_salt = None
        available_transitions = self._module.format_transitions(self._current_node)
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

        self._transcript.append(
            Message(
                role="assistant",
                content=result.response,
                metadata={"node_id": self._current_node},
            )
        )

        # Post-response: always-edge fires after the agent speaks (linear flow).
        always_target = self._find_always_transition(node)
        if always_target:
            self._apply_transition(turn_result, always_target)

        # End/transfer node with a prompt: agent spoke, now end the call.
        if (node.is_end_node() or node.is_transfer_node()) and not turn_result.transitioned_to:
            turn_result.end_call_invoked = True
            self._end_call_invoked = True

        return turn_result

    def _apply_transition(self, turn_result: TurnResult, target: str) -> None:
        """Record a transition to the given target node."""
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
        self._transcript.append(
            Message(
                role="tool",
                content=f"Transitioned to {target}",
                metadata={"tool_name": f"route_to_{target}", "node_id": target},
            )
        )

    def _evaluate_logic_node(self, state_module: StateModule) -> TurnResult:
        """Evaluate a logic node's equation transitions deterministically.

        Iterates transitions top-to-bottom (matching Retell's eval order),
        evaluates each equation against dynamic variables, returns first match.
        """
        turn_result = TurnResult(response="")
        fallback_target: str | None = None

        for transition in state_module.transitions:
            if transition.condition.type == "always":
                fallback_target = transition.target_node_id
                continue
            if not transition.condition.equations:
                continue
            combiner = all if transition.condition.logical_operator == "and" else any
            if combiner(
                evaluate_equation(clause, self._dynamic_variables)
                for clause in transition.condition.equations
            ):
                self._apply_transition(turn_result, transition.target_node_id)
                break
        else:
            # No equation matched — use always fallback if present
            if fallback_target:
                self._apply_transition(turn_result, fallback_target)

        return turn_result

    async def _evaluate_extract_node(
        self,
        node: AgentNode,
        state_module: StateModule,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Extract variables via LLM, then evaluate equations deterministically."""
        user_message = self._last_user_message()

        # Build a dynamic dspy.Signature for variable extraction
        docstring = expand_snippets(state_module.instructions, self.graph.snippets)
        docstring = substitute_variables(docstring, self._dynamic_variables)
        attrs: dict = {
            "__doc__": docstring,
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

        # Call LLM to extract variables
        result = await call_llm(
            self.model,
            sig,
            on_error=on_error,
            no_cache=self._no_cache,
            predictor_class=dspy.Predict,
            conversation_history=self._format_transcript(self._transcript),
            user_message=user_message,
        )

        # Store extracted values in dynamic variables
        extracted = {}
        for var in node.variables_to_extract:
            value = getattr(result, var.name, None)
            if value is not None:
                self._dynamic_variables[var.name] = str(value)
                extracted[var.name] = str(value)

        # Record extraction in transcript
        if extracted:
            parts = [f"{k}={v}" for k, v in extracted.items()]
            self._transcript.append(
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

        # Delegate to equation routing
        return self._evaluate_logic_node(state_module)

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
