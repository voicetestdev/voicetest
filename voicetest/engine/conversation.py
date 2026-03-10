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
from voicetest.engine.modules import RunContext
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

        self._split_transitions = self.options.split_transitions if self.options else False
        self._no_cache = self.options.no_cache if self.options else False
        self._module = ConversationModule(graph, use_split_transitions=self._split_transitions)

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
        """Process graph from current position until the agent speaks or settles.

        Traverses silent nodes (logic, extract) automatically, stopping when
        a conversation node produces speech or no transitions remain.
        """
        max_hops = 20
        accumulated_tool_calls: list[ToolCall] = []

        for _ in range(max_hops):
            result = await self._process_node(on_token=on_token, on_error=on_error)
            accumulated_tool_calls.extend(result.tool_calls)

            if result.response:
                result.tool_calls = accumulated_tool_calls
                return result

            if result.transitioned_to is None:
                break

        return TurnResult(response="", tool_calls=accumulated_tool_calls)

    async def _process_node(
        self,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Process the current node once. Returns result with response and transition info.

        For conversation nodes: calls LLM, gets response, evaluates transitions.
        For logic nodes: evaluates equations deterministically.
        For extract nodes: extracts variables via LLM, then evaluates equations.
        """
        # Get the state module for current node
        state_module = self._module.get_state_module(self._current_node)
        if state_module is None:
            raise ValueError(f"Unknown node: {self._current_node}")

        user_message = self._last_user_message()

        # Extract nodes: LLM extracts variables, then evaluate equations
        node = self.graph.nodes[self._current_node]
        if node.is_extract_node():
            return await self._evaluate_extract_node(node, state_module, on_error=on_error)

        # Logic nodes: evaluate equations deterministically, skip LLM
        if self._is_logic_node(state_module):
            return self._evaluate_logic_node(state_module)

        # Expand static snippets first, then dynamic variables
        general_instructions = expand_snippets(self._module.instructions, self.graph.snippets)
        state_instructions = expand_snippets(state_module.instructions, self.graph.snippets)
        general_instructions = substitute_variables(general_instructions, self._dynamic_variables)
        state_instructions = substitute_variables(state_instructions, self._dynamic_variables)

        # Build context for state execution
        ctx = RunContext(
            conversation_history=self._format_transcript(self._transcript),
            user_message=user_message,
            dynamic_variables=self._dynamic_variables,
            available_transitions=self._module.format_transitions(self._current_node),
            general_instructions=general_instructions,
            state_instructions=state_instructions,
        )

        # Build kwargs for the response LLM call
        response_kwargs = {
            "general_instructions": ctx.general_instructions,
            "state_instructions": ctx.state_instructions,
            "conversation_history": ctx.conversation_history,
            "user_message": ctx.user_message,
        }

        # Only pass available_transitions when the signature expects it (combined mode)
        cache_salt = None
        if state_module.transitions and not state_module.use_split_transitions:
            response_kwargs["available_transitions"] = ctx.available_transitions
        elif state_module.use_split_transitions and state_module.transitions:
            # Split mode: the response signature omits available_transitions,
            # so the cache key won't change when outbound edges are modified.
            # Inject a fingerprint via LM metadata to bust the cache.
            cache_salt = hashlib.sha256(
                json.dumps(
                    [t.model_dump() for t in ctx.available_transitions], sort_keys=True
                ).encode()
            ).hexdigest()[:16]

        # Call LLM with the state module's signature
        result = await call_llm(
            self.model,
            state_module._response_signature,
            on_token=on_token,
            stream_field="response" if on_token else None,
            on_error=on_error,
            cache_salt=cache_salt,
            no_cache=self._no_cache,
            **response_kwargs,
        )

        # Build turn result
        turn_result = TurnResult(response=result.response)
        generating_node = self._current_node

        # Determine transition target
        if state_module.use_split_transitions and state_module.transitions:
            # Split mode: second LLM call to evaluate transitions separately
            # Build full conversation context including current turn
            full_history = ctx.conversation_history
            if user_message:
                full_history += f"\nUSER: {user_message}"
            transition_result = await call_llm(
                self.model,
                self._module._transition_signature,
                on_error=on_error,
                no_cache=self._no_cache,
                conversation_history=full_history,
                agent_response=result.response,
                available_transitions=ctx.available_transitions,
            )
            transition_target = transition_result.transition_to.strip().lower()
        else:
            # Combined mode: transition comes from the response call
            transition_target = getattr(result, "transition_to", "none")
            if transition_target:
                transition_target = transition_target.strip().lower()

        if (
            transition_target
            and transition_target != "none"
            and transition_target in self.graph.nodes
        ):
            self._apply_transition(turn_result, transition_target)
        elif turn_result.transitioned_to is None:
            # No LLM-chosen transition: check for always-edge fallback
            always_target = self._find_always_transition(node)
            if always_target:
                self._apply_transition(turn_result, always_target)

        # Terminal node: no transitions defined and no always-edge fired
        if turn_result.transitioned_to is None and not node.transitions:
            turn_result.end_call_invoked = True
            self._end_call_invoked = True

        # Record agent response with the node that generated it
        self._transcript.append(
            Message(
                role="assistant",
                content=result.response,
                metadata={"node_id": generating_node},
            )
        )

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

    def _is_logic_node(self, state_module: StateModule) -> bool:
        """Check if a node is a logic node (equation transitions with optional always fallback)."""
        if not state_module.transitions:
            return False
        return all(
            t.condition.type in ("equation", "always") for t in state_module.transitions
        ) and any(t.condition.type == "equation" for t in state_module.transitions)

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
        attrs: dict = {
            "__doc__": "Extract structured variables from the conversation.",
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
