"""End-to-end tests for the chat WebSocket endpoint.

Exercises the full path: POST /api/agents/{id}/chats/start → connect
/api/chats/{id}/ws → send `message` → receive `transcript_update`. The
ConversationEngine.advance call is patched so tests don't hit a real LLM.
"""

from unittest.mock import AsyncMock
from unittest.mock import patch

from voicetest.engine.conversation import ConversationEngine
from voicetest.engine.conversation import TurnResult
from voicetest.models.results import Message


def _build_agent(db_client, sample_retell_config) -> str:
    agent_resp = db_client.post(
        "/api/agents",
        json={"name": "Chat WS Agent", "config": sample_retell_config},
    )
    return agent_resp.json()["id"]


def _start_chat(db_client, agent_id: str) -> str:
    resp = db_client.post(f"/api/agents/{agent_id}/chats/start", json={})
    assert resp.status_code == 200
    return resp.json()["chat_id"]


class TestChatWebSocket:
    """Lifecycle coverage for /api/chats/{chat_id}/ws."""

    def test_chat_ws_sends_state_on_connect(self, db_client, sample_retell_config):
        agent_id = _build_agent(db_client, sample_retell_config)
        chat_id = _start_chat(db_client, agent_id)

        with db_client.websocket_connect(f"/api/chats/{chat_id}/ws") as ws:
            state = ws.receive_json()

        assert state["type"] == "state"
        assert state["chat"]["id"] == chat_id
        assert "transcript" in state["chat"]

    def test_chat_ws_returns_error_for_unknown_chat(self, db_client):
        with db_client.websocket_connect("/api/chats/nonexistent/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_chat_ws_broadcasts_transcript_after_user_message(
        self, db_client, sample_retell_config
    ):
        """Sending a `message` advances the engine and broadcasts the updated transcript."""
        agent_id = _build_agent(db_client, sample_retell_config)
        chat_id = _start_chat(db_client, agent_id)

        # Patch the engine's advance() to skip LLM work and push a fake reply onto the
        # transcript. add_user_message is patched to append the user turn synchronously.
        # `transcript` is a property returning a copy, so we write through `_transcript`.
        async def fake_add_user_message(self_engine, content):
            self_engine._transcript.append(Message(role="user", content=content))

        async def fake_advance(self_engine, on_token=None):
            self_engine._transcript.append(Message(role="assistant", content="canned reply"))
            return TurnResult(response="canned reply", end_call_invoked=False)

        with (
            patch.object(ConversationEngine, "add_user_message", fake_add_user_message),
            patch.object(ConversationEngine, "advance", fake_advance),
            db_client.websocket_connect(f"/api/chats/{chat_id}/ws") as ws,
        ):
            ws.receive_json()  # state
            ws.send_json({"type": "message", "content": "hello there"})

            # First transcript_update is the user-msg echo (process_message broadcasts twice).
            msg = ws.receive_json()
            assert msg["type"] == "transcript_update"
            assert any(m["content"] == "hello there" for m in msg["transcript"])

            # Second transcript_update includes the agent's reply.
            msg = ws.receive_json()
            assert msg["type"] == "transcript_update"
            assert any(m["content"] == "canned reply" for m in msg["transcript"])

    def test_chat_ws_end_chat_closes_session(self, db_client, sample_retell_config):
        """Sending `end_chat` removes the session from ChatManager and closes the WS."""
        from voicetest.web.chat import ChatManager

        agent_id = _build_agent(db_client, sample_retell_config)
        chat_id = _start_chat(db_client, agent_id)

        chat_manager = db_client.app.state.container.resolve(ChatManager)
        assert chat_manager.get_active_chat(chat_id) is not None

        with db_client.websocket_connect(f"/api/chats/{chat_id}/ws") as ws:
            ws.receive_json()  # state
            # Patch save_call_as_run to avoid evaluating metrics on an empty transcript.
            with patch(
                "voicetest.services.runs.RunService.save_call_as_run",
                AsyncMock(return_value=None),
            ):
                ws.send_json({"type": "end_chat"})

        assert chat_manager.get_active_chat(chat_id) is None
