"""Tests for voicetest text chat manager."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from voicetest.chat import ActiveChat
from voicetest.chat import ChatManager


@pytest.fixture
def chat_manager():
    """Create a ChatManager instance."""
    return ChatManager()


@pytest.fixture
def call_repo():
    """Create a mock CallRepository."""
    repo = MagicMock()
    repo.create.return_value = {
        "id": "test-chat-id",
        "agent_id": "agent-1",
        "room_name": "chat-test1234",
        "status": "pending",
        "transcript_json": [],
        "started_at": "2026-01-01T00:00:00",
        "ended_at": None,
    }
    repo.update_status.return_value = {
        "id": "test-chat-id",
        "status": "active",
    }
    repo.end_call.return_value = {
        "id": "test-chat-id",
        "status": "ended",
        "ended_at": "2026-01-01T00:01:00",
    }
    repo.update_transcript = MagicMock()
    repo.get.return_value = {
        "id": "test-chat-id",
        "agent_id": "agent-1",
        "room_name": "chat-test1234",
        "status": "active",
        "transcript_json": [],
        "started_at": "2026-01-01T00:00:00",
        "ended_at": None,
    }
    return repo


class TestChatManagerStartChat:
    """Tests for ChatManager.start_chat."""

    @pytest.mark.asyncio
    async def test_start_chat_returns_chat_id(self, chat_manager, call_repo, single_node_graph):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )

        assert "chat_id" in result
        assert result["chat_id"] == "test-chat-id"

    @pytest.mark.asyncio
    async def test_start_chat_creates_call_record(self, chat_manager, call_repo, single_node_graph):
        await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )

        call_repo.create.assert_called_once()
        args = call_repo.create.call_args
        assert args[0][0] == "agent-1"
        assert args[0][1].startswith("chat-")

    @pytest.mark.asyncio
    async def test_start_chat_sets_status_active(self, chat_manager, call_repo, single_node_graph):
        await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )

        call_repo.update_status.assert_called_once_with("test-chat-id", "active")

    @pytest.mark.asyncio
    async def test_start_chat_registers_active_session(
        self, chat_manager, call_repo, single_node_graph
    ):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )

        active = chat_manager.get_active_chat(result["chat_id"])
        assert active is not None
        assert active.agent_id == "agent-1"
        assert active.engine is not None

    @pytest.mark.asyncio
    async def test_start_chat_with_graph_default_model(
        self, chat_manager, call_repo, single_node_graph
    ):
        single_node_graph.default_model = "openai/gpt-4o"
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model=None
        )

        active = chat_manager.get_active_chat(result["chat_id"])
        assert active.engine.model == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_start_chat_with_dynamic_variables(
        self, chat_manager, call_repo, single_node_graph
    ):
        variables = {"name": "Alice", "company": "Acme"}
        result = await chat_manager.start_chat(
            "agent-1",
            single_node_graph,
            call_repo,
            agent_model="groq/llama-3.1-8b-instant",
            dynamic_variables=variables,
        )

        active = chat_manager.get_active_chat(result["chat_id"])
        assert active.engine._dynamic_variables == variables

    @pytest.mark.asyncio
    async def test_start_chat_without_dynamic_variables(
        self, chat_manager, call_repo, single_node_graph
    ):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )

        active = chat_manager.get_active_chat(result["chat_id"])
        assert active.engine._dynamic_variables == {}


class TestChatManagerEndChat:
    """Tests for ChatManager.end_chat."""

    @pytest.mark.asyncio
    async def test_end_chat_cleans_up_session(self, chat_manager, call_repo, single_node_graph):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )
        chat_id = result["chat_id"]

        await chat_manager.end_chat(chat_id, call_repo)

        assert chat_manager.get_active_chat(chat_id) is None

    @pytest.mark.asyncio
    async def test_end_chat_calls_repo_end(self, chat_manager, call_repo, single_node_graph):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )

        await chat_manager.end_chat(result["chat_id"], call_repo)

        call_repo.end_call.assert_called_once_with("test-chat-id")

    @pytest.mark.asyncio
    async def test_end_chat_sets_cancel_event(self, chat_manager, call_repo, single_node_graph):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )
        chat_id = result["chat_id"]
        active = chat_manager.get_active_chat(chat_id)

        await chat_manager.end_chat(chat_id, call_repo)

        assert active.cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_end_nonexistent_chat_falls_through(self, chat_manager, call_repo):
        await chat_manager.end_chat("nonexistent", call_repo)

        call_repo.end_call.assert_called_once_with("nonexistent")


class TestChatManagerWebSocket:
    """Tests for WebSocket management."""

    @pytest.mark.asyncio
    async def test_register_websocket(self, chat_manager, call_repo, single_node_graph):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )
        chat_id = result["chat_id"]
        ws = MagicMock()

        queued = chat_manager.register_websocket(chat_id, ws)

        assert queued == []
        active = chat_manager.get_active_chat(chat_id)
        assert ws in active.websockets

    @pytest.mark.asyncio
    async def test_unregister_websocket(self, chat_manager, call_repo, single_node_graph):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )
        chat_id = result["chat_id"]
        ws = MagicMock()
        chat_manager.register_websocket(chat_id, ws)

        chat_manager.unregister_websocket(chat_id, ws)

        active = chat_manager.get_active_chat(chat_id)
        assert ws not in active.websockets

    @pytest.mark.asyncio
    async def test_register_returns_queued_messages(
        self, chat_manager, call_repo, single_node_graph
    ):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )
        chat_id = result["chat_id"]

        # Broadcast while no WebSocket connected (queues messages)
        await chat_manager._broadcast_update(chat_id, {"type": "test"})

        ws = MagicMock()
        queued = chat_manager.register_websocket(chat_id, ws)

        assert len(queued) == 1
        assert '"type": "test"' in queued[0]

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_connected_websockets(
        self, chat_manager, call_repo, single_node_graph
    ):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )
        chat_id = result["chat_id"]

        ws = AsyncMock()
        chat_manager.register_websocket(chat_id, ws)

        await chat_manager._broadcast_update(chat_id, {"type": "test_msg"})

        ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_sockets(self, chat_manager, call_repo, single_node_graph):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )
        chat_id = result["chat_id"]

        ws = AsyncMock()
        ws.send_text.side_effect = Exception("Connection closed")
        chat_manager.register_websocket(chat_id, ws)

        await chat_manager._broadcast_update(chat_id, {"type": "test_msg"})

        active = chat_manager.get_active_chat(chat_id)
        assert ws not in active.websockets

    @pytest.mark.asyncio
    async def test_register_for_nonexistent_chat_returns_empty(self, chat_manager):
        ws = MagicMock()
        queued = chat_manager.register_websocket("nonexistent", ws)
        assert queued == []


class TestChatManagerProcessMessage:
    """Tests for ChatManager.process_message."""

    @pytest.mark.asyncio
    async def test_process_message_skips_cancelled_chat(
        self, chat_manager, call_repo, single_node_graph
    ):
        result = await chat_manager.start_chat(
            "agent-1", single_node_graph, call_repo, agent_model="groq/llama-3.1-8b-instant"
        )
        chat_id = result["chat_id"]
        active = chat_manager.get_active_chat(chat_id)
        active.cancel_event.set()

        # Should return without processing
        await chat_manager.process_message(chat_id, "hello", call_repo)

        # Transcript should be empty (no processing happened)
        assert active.transcript == []

    @pytest.mark.asyncio
    async def test_process_message_skips_nonexistent_chat(self, chat_manager, call_repo):
        # Should not raise
        await chat_manager.process_message("nonexistent", "hello", call_repo)


class TestActiveChatDataclass:
    """Tests for ActiveChat dataclass."""

    def test_active_chat_defaults(self):
        chat = ActiveChat(
            chat_id="test-id",
            agent_id="agent-1",
            engine=MagicMock(),
        )
        assert chat.websockets == set()
        assert chat.transcript == []
        assert chat.message_queue == []
        assert not chat.cancel_event.is_set()
        assert chat.processing is False
