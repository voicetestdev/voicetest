"""Tests for voice participant builders."""

from unittest.mock import patch

from voicetest.livecall.participant import CascadeParticipant
from voicetest.livecall.participant import VoiceParticipant


class TestCascadeParticipant:
    """Characterization of the cascade AgentSession construction."""

    @patch("voicetest.livecall.participant.AgentSession")
    def test_build_session_passes_components(self, mock_session):
        stt, llm, tts, vad = object(), object(), object(), object()
        participant = CascadeParticipant(stt=stt, llm=llm, tts=tts, vad=vad)

        participant.build_session()

        mock_session.assert_called_once_with(
            stt=stt, llm=llm, tts=tts, vad=vad, allow_interruptions=False
        )

    @patch("voicetest.livecall.participant.AgentSession")
    def test_allow_interruptions_defaults_false(self, mock_session):
        participant = CascadeParticipant(stt=object(), llm=object(), tts=object(), vad=object())

        participant.build_session()

        _, kwargs = mock_session.call_args
        assert kwargs["allow_interruptions"] is False

    @patch("voicetest.livecall.participant.AgentSession")
    def test_allow_interruptions_override(self, mock_session):
        participant = CascadeParticipant(
            stt=object(), llm=object(), tts=object(), vad=object(), allow_interruptions=True
        )

        participant.build_session()

        _, kwargs = mock_session.call_args
        assert kwargs["allow_interruptions"] is True

    def test_exposes_intended_text(self):
        participant = CascadeParticipant(stt=object(), llm=object(), tts=object(), vad=object())
        assert participant.intended_text_available is True


class TestVoiceParticipantContract:
    """The interface must not assume intended text is available.

    Guards the S2S seam: a future RealtimeParticipant has no separable LLM and
    no intended-text channel. Consumers must treat intended text as optional."""

    def test_participant_without_intended_text_satisfies_protocol(self):
        class FakeRealtimeParticipant:
            intended_text_available = False

            def build_session(self):
                return "session"

        participant: VoiceParticipant = FakeRealtimeParticipant()

        assert participant.intended_text_available is False
        assert participant.build_session() == "session"
