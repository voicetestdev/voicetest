"""Text chat management for voicetest.

Handles text-based live conversations using ConversationEngine directly.
No LiveKit or audio infrastructure required.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from dataclasses import field
import logging
from typing import Any
from uuid import uuid4

from voicetest.broadcast import BroadcastBus
from voicetest.engine.conversation import ConversationEngine
from voicetest.exceptions import QuotaExhaustedError
from voicetest.models.agent import AgentGraph
from voicetest.models.test_case import RunOptions
from voicetest.services.settings import SettingsService
from voicetest.settings import resolve_model


logger = logging.getLogger(__name__)


@dataclass
class ActiveChat:
    """Tracks state of an active chat session."""

    chat_id: str
    agent_id: str
    engine: ConversationEngine
    transcript: list = field(default_factory=list)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    processing: bool = False


class ChatManager:
    """Manages text-based chat sessions with agents."""

    def __init__(self, settings_service: SettingsService) -> None:
        self._active_chats: dict[str, ActiveChat] = {}
        self._bus = BroadcastBus()
        self._settings = settings_service

    async def start_chat(
        self,
        agent_id: str,
        graph: AgentGraph,
        call_repo: Any,
        agent_model: str | None = None,
        dynamic_variables: dict | None = None,
    ) -> dict:
        """Start a text chat session.

        Creates a Call record for persistence and instantiates a ConversationEngine.

        Args:
            agent_id: ID of the agent to chat with.
            graph: The agent graph configuration.
            call_repo: Repository for persisting call/chat records.
            agent_model: LLM model. Reads from settings if None.
            dynamic_variables: Variables for template substitution in prompts.

        Returns:
            Dict with chat_id.
        """
        chat_id = str(uuid4())
        room_name = f"chat-{chat_id[:8]}"

        settings = self._settings.get_settings()
        if agent_model is None:
            agent_model = settings.models.agent

        # Resolve model: settings agent_model, then graph default, then fallback
        model = resolve_model(agent_model, graph.default_model)

        engine = ConversationEngine(graph, model, RunOptions(), dynamic_variables=dynamic_variables)

        # Persist using the Call table
        call_record = call_repo.create(agent_id, room_name)
        call_repo.update_status(call_record["id"], "active")

        active_chat = ActiveChat(
            chat_id=call_record["id"],
            agent_id=agent_id,
            engine=engine,
        )
        self._active_chats[call_record["id"]] = active_chat
        self._bus.start(call_record["id"])

        return {"chat_id": call_record["id"]}

    async def process_message(
        self,
        chat_id: str,
        content: str,
        call_repo: Any,
    ) -> None:
        """Process a user message and stream the agent response.

        Args:
            chat_id: The chat session ID.
            content: The user's message text.
            call_repo: Repository for persisting transcript updates.
        """
        if chat_id not in self._active_chats:
            return

        active_chat = self._active_chats[chat_id]
        if active_chat.cancel_event.is_set():
            return

        active_chat.processing = True

        try:
            # Add user message to engine
            await active_chat.engine.add_user_message(content)

            # Update transcript with user message
            active_chat.transcript = [m.model_dump() for m in active_chat.engine.transcript]
            call_repo.update_transcript(chat_id, active_chat.transcript)

            # Broadcast user message in transcript
            await self._broadcast_update(
                chat_id,
                {
                    "type": "transcript_update",
                    "transcript": active_chat.transcript,
                },
            )

            # Define streaming token callback
            async def on_token(token: str, source: str) -> None:
                await self._broadcast_update(
                    chat_id,
                    {"type": "token", "content": token},
                )

            # Process the turn
            turn_result = await active_chat.engine.advance(
                on_token=on_token,
            )

            # Update transcript with agent response
            active_chat.transcript = [m.model_dump() for m in active_chat.engine.transcript]
            call_repo.update_transcript(chat_id, active_chat.transcript)

            # Broadcast full transcript update
            await self._broadcast_update(
                chat_id,
                {
                    "type": "transcript_update",
                    "transcript": active_chat.transcript,
                },
            )

            # If agent ended the call, broadcast and clean up the session
            if turn_result.end_call_invoked:
                await self._broadcast_update(
                    chat_id,
                    {"type": "chat_ended", "reason": "agent_ended"},
                )
                call_repo.end_call(chat_id)
                del self._active_chats[chat_id]
                self._bus.end(chat_id)

        except QuotaExhaustedError as e:
            logger.warning("Quota exhausted during chat %s: %s", chat_id, e)
            await self._broadcast_update(
                chat_id,
                {
                    "type": "quota_exhausted",
                    "message": str(e),
                    "reset_message": e.reset_message,
                },
            )
        except Exception as e:
            logger.exception("Error processing chat message for %s", chat_id)
            await self._broadcast_update(
                chat_id,
                {"type": "error", "message": str(e)},
            )
        finally:
            active_chat.processing = False

    async def end_chat(self, chat_id: str, call_repo: Any) -> dict | None:
        """End a chat session and clean up resources."""
        if chat_id not in self._active_chats:
            return call_repo.end_call(chat_id)

        active_chat = self._active_chats[chat_id]
        active_chat.cancel_event.set()

        await self._broadcast_update(chat_id, {"type": "chat_ended"})

        for ws in list(self._bus.subscribers(chat_id)):
            with contextlib.suppress(Exception):
                await ws.close()

        del self._active_chats[chat_id]
        self._bus.end(chat_id)

        return call_repo.end_call(chat_id)

    def get_active_chat(self, chat_id: str) -> ActiveChat | None:
        """Get active chat state."""
        return self._active_chats.get(chat_id)

    async def attach_websocket(self, chat_id: str, websocket: Any) -> None:
        """Subscribe a WebSocket to chat updates (after replaying any backlog)."""
        await self._bus.attach(chat_id, websocket)

    def detach_websocket(self, chat_id: str, websocket: Any) -> None:
        self._bus.detach(chat_id, websocket)

    async def _broadcast_update(self, chat_id: str, data: dict) -> None:
        await self._bus.broadcast(chat_id, data)
