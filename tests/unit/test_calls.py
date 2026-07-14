"""Tests for live-call transcript helpers."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.web.calls import ActiveCall
from voicetest.web.calls import CallManager
from voicetest.web.calls import LiveKitConfig
from voicetest.web.calls import append_intended
from voicetest.web.calls import merge_observed_heard


def _add_intended(transcript, turn_messages, role, content, turn_id):
    """Mimic _monitor_agent_output appending an intended turn and indexing it."""
    message = {"role": role, "content": content}
    transcript.append(message)
    if turn_id is not None:
        turn_messages[(role, turn_id)] = message
    return message


class TestMergeObservedHeard:
    def test_correlates_heard_to_its_turn(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "hello there", turn_id=1)

        merge_observed_heard(transcript, turns, "assistant", "hello thair", turn_id=1)

        assert transcript[0]["content"] == "hello there"
        assert transcript[0]["metadata"]["audio"]["heard"] == "hello thair"

    def test_multiple_finals_of_one_turn_concatenate(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "Hello. How can I help?", turn_id=1)

        merge_observed_heard(transcript, turns, "assistant", "Hello.", turn_id=1)
        merge_observed_heard(transcript, turns, "assistant", "How can I help?", turn_id=1)

        assert len(transcript) == 1  # no phantom turn
        assert transcript[0]["metadata"]["audio"]["heard"] == "Hello. How can I help?"

    def test_distinct_turns_land_on_their_own_message(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "first", turn_id=1)
        _add_intended(transcript, turns, "assistant", "second", turn_id=2)

        merge_observed_heard(transcript, turns, "assistant", "second heard", turn_id=2)
        merge_observed_heard(transcript, turns, "assistant", "first heard", turn_id=1)

        assert transcript[0]["metadata"]["audio"]["heard"] == "first heard"
        assert transcript[1]["metadata"]["audio"]["heard"] == "second heard"

    def test_appends_standalone_when_turn_unknown(self):
        transcript, turns = [], {}

        merge_observed_heard(transcript, turns, "assistant", "orphan a", turn_id=7)
        merge_observed_heard(transcript, turns, "assistant", "orphan b", turn_id=7)

        assert len(transcript) == 1
        assert transcript[0]["role"] == "assistant"
        assert transcript[0]["metadata"]["audio"]["heard"] == "orphan a orphan b"

    def test_skips_empty_or_missing(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "hi", turn_id=1)

        merge_observed_heard(transcript, turns, "assistant", "", turn_id=1)
        merge_observed_heard(transcript, turns, None, "x", turn_id=1)

        assert "metadata" not in transcript[0]
        assert len(transcript) == 1

    def test_preserves_other_metadata(self):
        transcript, turns = [], {}
        message = _add_intended(transcript, turns, "assistant", "hello", turn_id=1)
        message["metadata"] = {"foo": "bar"}

        merge_observed_heard(transcript, turns, "assistant", "hallo", turn_id=1)

        assert transcript[0]["metadata"]["foo"] == "bar"
        assert transcript[0]["metadata"]["audio"]["heard"] == "hallo"

    def test_intended_after_observed_fills_standalone_no_duplicate(self):
        transcript, turns = [], {}
        merge_observed_heard(transcript, turns, "assistant", "helo", turn_id=1)
        assert len(transcript) == 1

        append_intended(transcript, turns, {"role": "assistant", "content": "hello"}, turn_id=1)

        assert len(transcript) == 1
        assert transcript[0]["content"] == "hello"
        assert transcript[0]["metadata"]["audio"]["heard"] == "helo"

    def test_intended_first_appends_and_indexes(self):
        transcript, turns = [], {}

        append_intended(transcript, turns, {"role": "assistant", "content": "hi"}, turn_id=2)

        assert len(transcript) == 1
        assert turns[("assistant", 2)]["content"] == "hi"

    def test_same_turn_id_different_roles_do_not_collide(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "agent one", turn_id=1)
        _add_intended(transcript, turns, "user", "caller one", turn_id=1)

        merge_observed_heard(transcript, turns, "assistant", "agent heard", turn_id=1)
        merge_observed_heard(transcript, turns, "user", "caller heard", turn_id=1)

        assert transcript[0]["metadata"]["audio"]["heard"] == "agent heard"
        assert transcript[1]["metadata"]["audio"]["heard"] == "caller heard"


class TestStartCall:
    async def _start(self, persona):
        settings = MagicMock()
        settings.models.simulator = None
        settings.models.agent = None
        settings_svc = MagicMock()
        settings_svc.get_settings.return_value = settings

        cm = CallManager(settings_service=settings_svc, config=LiveKitConfig(voice_backend="local"))
        cm.create_room = AsyncMock()
        cm.generate_token = MagicMock(return_value="tok")
        cm._monitor_agent_output = MagicMock()

        call_repo = MagicMock()
        call_repo.create.return_value = {"id": "c1", "room_name": "r", "status": "connecting"}
        graph = AgentGraph(entry_node_id="n", nodes={}, source_type="test", source_metadata={})

        captured: list[list] = []

        def fake_popen(cmd, **kwargs):
            captured.append(cmd)
            return MagicMock()

        with (
            patch("voicetest.web.calls.subprocess.Popen", side_effect=fake_popen),
            patch("voicetest.web.calls.asyncio.create_task"),
        ):
            result = await cm.start_call("agent1", graph, call_repo, persona=persona)
        return captured, result

    def _launched_caller(self, captured):
        return any("voicetest.livecall.caller_worker" in c for c in captured)

    @pytest.mark.asyncio
    async def test_caller_model_resolved_when_simulator_unset(self):
        captured, _ = await self._start("## Goal\nx")
        caller_cmd = next(c for c in captured if "voicetest.livecall.caller_worker" in c)
        assert caller_cmd[caller_cmd.index("--model") + 1]

    @pytest.mark.asyncio
    async def test_empty_persona_still_launches_caller(self):
        captured, _ = await self._start("")
        assert self._launched_caller(captured)

    @pytest.mark.asyncio
    async def test_simulated_call_returns_no_browser_token(self):
        _, result = await self._start("## Goal\nx")
        assert not result["token"]

    @pytest.mark.asyncio
    async def test_human_call_returns_token_and_no_caller(self):
        captured, result = await self._start(None)
        assert result["token"]
        assert not self._launched_caller(captured)

    def _agent_cmd(self, captured):
        return next(c for c in captured if "voicetest.livecall.agent_worker" in c)

    @pytest.mark.asyncio
    async def test_agent_suppresses_user_transcript_when_simulated(self):
        captured, _ = await self._start("## Goal\nx")
        assert "--no-user-transcript" in self._agent_cmd(captured)

    @pytest.mark.asyncio
    async def test_agent_keeps_user_transcript_for_human_call(self):
        captured, _ = await self._start(None)
        assert "--no-user-transcript" not in self._agent_cmd(captured)


class TestEndWhenCallerDone:
    def _manager(self):
        cm = CallManager(settings_service=MagicMock(), config=LiveKitConfig())
        cm._sessions.close = AsyncMock()
        return cm

    @pytest.mark.asyncio
    async def test_saves_and_broadcasts_run_id_on_caller_exit(self):
        cm = self._manager()
        active = ActiveCall(call_id="c1", room_name="r")
        cm._sessions.register("c1", active)
        caller = MagicMock()
        caller.poll.return_value = 0
        on_caller_done = AsyncMock(return_value="run-1")

        await cm._end_when_caller_done("c1", caller, MagicMock(), on_caller_done)

        on_caller_done.assert_awaited_once_with("c1")
        assert active.cancel_event.is_set()
        _, payload = cm._sessions.close.call_args[0]
        assert payload == {"type": "call_ended", "run_id": "run-1"}

    @pytest.mark.asyncio
    async def test_closes_session_even_when_save_raises(self):
        cm = self._manager()
        active = ActiveCall(call_id="c3", room_name="r")
        cm._sessions.register("c3", active)
        caller = MagicMock()
        caller.poll.return_value = 0
        on_caller_done = AsyncMock(side_effect=RuntimeError("judge failed"))

        await cm._end_when_caller_done("c3", caller, MagicMock(), on_caller_done)

        cm._sessions.close.assert_awaited_once()
        _, payload = cm._sessions.close.call_args[0]
        assert payload == {"type": "call_ended", "run_id": None}

    @pytest.mark.asyncio
    async def test_skips_when_already_cancelled(self):
        cm = self._manager()
        active = ActiveCall(call_id="c2", room_name="r")
        active.cancel_event.set()
        cm._sessions.register("c2", active)
        caller = MagicMock()
        caller.poll.return_value = 0
        on_caller_done = AsyncMock()

        await cm._end_when_caller_done("c2", caller, MagicMock(), on_caller_done)

        on_caller_done.assert_not_awaited()
        cm._sessions.close.assert_not_awaited()


class TestCallerCommand:
    def _manager(self):
        return CallManager(settings_service=None, config=LiveKitConfig(voice_backend="local"))

    def test_caller_cmd_targets_caller_worker_with_persona(self):
        cm = self._manager()

        cmd = cm._caller_cmd("room1", "utok", "otok", "PERSONA TEXT", "model-x", max_turns=12)

        assert "voicetest.livecall.caller_worker" in cmd
        assert cmd[cmd.index("--token") + 1] == "utok"
        assert cmd[cmd.index("--observer-token") + 1] == "otok"
        assert cmd[cmd.index("--persona") + 1] == "PERSONA TEXT"
        assert cmd[cmd.index("--model") + 1] == "model-x"
        assert cmd[cmd.index("--max-turns") + 1] == "12"
        assert cmd[cmd.index("--backend") + 1] == "local"
