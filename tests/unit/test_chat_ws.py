"""End-to-end tests for the chat WebSocket endpoint.

Exercises the full path: POST /api/agents/{id}/chats/start → connect
/api/chats/{id}/ws → send `message` → receive `transcript_update`. The
real `ConversationEngine` runs; only `call_llm` (the LLM transport seam)
is stubbed so tests don't hit a real provider.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

from voicetest.web.chat import ChatManager


def _start_chat(db_client, agent_id: str) -> str:
    resp = db_client.post(f"/api/agents/{agent_id}/chats/start", json={})
    assert resp.status_code == 200
    return resp.json()["chat_id"]


async def _stub_llm(model, signature, **kwargs):
    """Return a minimal prediction shape covering both transition + response calls.

    The engine's response-generation path reads `.response`; transition-resolution
    reads `.objectives_complete` and `.transition_to`. We supply all three so a
    single stub works for either call, regardless of signature.
    """
    return SimpleNamespace(
        response="canned reply",
        objectives_complete=False,
        transition_to="none",
    )


class TestChatWebSocket:
    """Lifecycle coverage for /api/chats/{chat_id}/ws."""

    def test_chat_ws_sends_state_on_connect(self, db_client, make_agent, single_node_graph):
        agent_id = make_agent(graph=single_node_graph)["id"]
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
        self, db_client, make_agent, single_node_graph
    ):
        """Real engine runs end-to-end; only the LLM transport is stubbed.

        Single-node graph has no transitions, so `advance` makes exactly one
        `call_llm` invocation (for response generation). The engine's own
        transcript bookkeeping, snippet expansion, and broadcast emission all
        execute normally — only the LLM provider call is intercepted.
        """
        agent_id = make_agent(graph=single_node_graph)["id"]
        chat_id = _start_chat(db_client, agent_id)

        with (
            patch("voicetest.engine.conversation.call_llm", side_effect=_stub_llm),
            db_client.websocket_connect(f"/api/chats/{chat_id}/ws") as ws,
        ):
            ws.receive_json()  # state
            ws.send_json({"type": "message", "content": "hello there"})

            # process_message broadcasts twice: first the user turn, then the assistant reply.
            user_msg = ws.receive_json()
            assert user_msg["type"] == "transcript_update"
            assert any(m["content"] == "hello there" for m in user_msg["transcript"])

            agent_msg = ws.receive_json()
            assert agent_msg["type"] == "transcript_update"
            assert any(m["content"] == "canned reply" for m in agent_msg["transcript"])

    def test_chat_ws_end_chat_closes_session(self, db_client, make_agent, single_node_graph):
        """Sending `end_chat` removes the session from ChatManager and closes the WS."""
        agent_id = make_agent(graph=single_node_graph)["id"]
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
