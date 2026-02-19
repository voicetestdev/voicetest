"""Tests for audio round-trip evaluation module."""

import pytest

from voicetest.audio import AudioRoundTrip
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.test_case import RunOptions
from voicetest.settings import AudioSettings
from voicetest.settings import Settings


class TestAudioRoundTrip:
    """Tests for AudioRoundTrip class."""

    def test_default_urls(self):
        rt = AudioRoundTrip()
        assert rt.tts_base_url == "http://localhost:8002/v1"
        assert rt.stt_base_url == "http://localhost:8001/v1"

    def test_custom_urls(self):
        rt = AudioRoundTrip(
            tts_base_url="http://tts:9000/v1",
            stt_base_url="http://stt:9001/v1",
        )
        assert rt.tts_base_url == "http://tts:9000/v1"
        assert rt.stt_base_url == "http://stt:9001/v1"

    def test_trailing_slash_stripped(self):
        rt = AudioRoundTrip(tts_base_url="http://tts:9000/v1/")
        assert rt.tts_base_url == "http://tts:9000/v1"

    def test_from_settings_defaults(self):
        rt = AudioRoundTrip.from_settings()
        assert rt.tts_base_url == "http://localhost:8002/v1"
        assert rt.stt_base_url == "http://localhost:8001/v1"

    def test_from_settings_custom(self):
        settings = Settings(
            audio=AudioSettings(
                tts_url="http://custom-tts:5000/v1",
                stt_url="http://custom-stt:5001/v1",
            )
        )
        rt = AudioRoundTrip.from_settings(settings)
        assert rt.tts_base_url == "http://custom-tts:5000/v1"
        assert rt.stt_base_url == "http://custom-stt:5001/v1"


class TestTransformTranscript:
    """Tests for transform_transcript method."""

    @pytest.mark.asyncio
    async def test_user_messages_unchanged(self):
        """User messages should pass through without modification."""
        rt = AudioRoundTrip()

        # Patch round_trip to track calls
        calls = []

        async def mock_round_trip(text):
            calls.append(text)
            return f"heard: {text}"

        rt.round_trip = mock_round_trip

        transcript = [
            Message(role="user", content="Hello there"),
            Message(role="assistant", content="Hi! How can I help?"),
        ]

        result = await rt.transform_transcript(transcript)

        assert result[0].role == "user"
        assert result[0].content == "Hello there"
        assert "heard" not in result[0].metadata

    @pytest.mark.asyncio
    async def test_assistant_messages_get_heard(self):
        """Assistant messages should get metadata['heard'] populated."""
        rt = AudioRoundTrip()

        async def mock_round_trip(text):
            return f"heard: {text}"

        rt.round_trip = mock_round_trip

        transcript = [
            Message(role="user", content="What is your number?"),
            Message(role="assistant", content="Call 415-555-1234"),
        ]

        result = await rt.transform_transcript(transcript)

        assert result[1].role == "assistant"
        assert result[1].content == "Call 415-555-1234"
        assert result[1].metadata["heard"] == "heard: Call 415-555-1234"

    @pytest.mark.asyncio
    async def test_original_transcript_not_mutated(self):
        """transform_transcript should deep-copy, not mutate the original."""
        rt = AudioRoundTrip()

        async def mock_round_trip(text):
            return "heard"

        rt.round_trip = mock_round_trip

        transcript = [
            Message(role="assistant", content="Hello"),
        ]

        result = await rt.transform_transcript(transcript)

        assert "heard" in result[0].metadata
        assert "heard" not in transcript[0].metadata

    @pytest.mark.asyncio
    async def test_empty_assistant_message_skipped(self):
        """Empty assistant messages should not be round-tripped."""
        rt = AudioRoundTrip()
        calls = []

        async def mock_round_trip(text):
            calls.append(text)
            return text

        rt.round_trip = mock_round_trip

        transcript = [
            Message(role="assistant", content=""),
            Message(role="assistant", content="   "),
        ]

        result = await rt.transform_transcript(transcript)

        assert len(calls) == 0
        assert "heard" not in result[0].metadata
        assert "heard" not in result[1].metadata

    @pytest.mark.asyncio
    async def test_round_trip_error_logged_not_raised(self):
        """If round_trip fails, the error is logged but the message passes through."""
        rt = AudioRoundTrip()

        async def failing_round_trip(text):
            raise ConnectionError("TTS service down")

        rt.round_trip = failing_round_trip

        transcript = [
            Message(role="assistant", content="Hello"),
        ]

        result = await rt.transform_transcript(transcript)

        assert result[0].content == "Hello"
        assert "heard" not in result[0].metadata


class TestRunOptions:
    """Tests for audio_eval option in RunOptions."""

    def test_audio_eval_default_false(self):
        options = RunOptions()
        assert options.audio_eval is False

    def test_audio_eval_enabled(self):
        options = RunOptions(audio_eval=True)
        assert options.audio_eval is True


class TestAudioSettings:
    """Tests for AudioSettings in Settings."""

    def test_default_audio_settings(self):
        settings = Settings()
        assert settings.audio.tts_url == "http://localhost:8002/v1"
        assert settings.audio.stt_url == "http://localhost:8001/v1"
        assert settings.run.audio_eval is False

    def test_audio_eval_in_run_settings(self):
        settings = Settings(run={"audio_eval": True})
        assert settings.run.audio_eval is True

    def test_save_and_load_audio_settings(self, tmp_path):
        from voicetest.settings import load_settings
        from voicetest.settings import save_settings

        settings_file = tmp_path / ".voicetest.toml"

        original = Settings(
            run={"audio_eval": True},
            audio=AudioSettings(
                tts_url="http://custom:8002/v1",
                stt_url="http://custom:8001/v1",
            ),
        )
        save_settings(original, settings_file)
        loaded = load_settings(settings_file)

        assert loaded.run.audio_eval is True
        assert loaded.audio.tts_url == "http://custom:8002/v1"
        assert loaded.audio.stt_url == "http://custom:8001/v1"

    def test_toml_contains_audio_section(self, tmp_path):
        from voicetest.settings import save_settings

        settings_file = tmp_path / ".voicetest.toml"

        settings = Settings()
        save_settings(settings, settings_file)
        content = settings_file.read_text()

        assert "[audio]" in content
        assert "tts_url" in content
        assert "stt_url" in content
        assert "audio_eval" in content


class TestMetricResult:
    """Tests for audio_metric_results in TestResult."""

    def test_audio_metric_results_default_empty(self):
        from voicetest.models.results import TestResult

        result = TestResult(test_name="test", status="pass")
        assert result.audio_metric_results == []

    def test_audio_metric_results_populated(self):
        from voicetest.models.results import TestResult

        result = TestResult(
            test_name="test",
            status="pass",
            audio_metric_results=[
                MetricResult(
                    metric="Phone number spoken correctly",
                    passed=False,
                    reasoning="TTS said 'four hundred fifteen' instead of '4-1-5'",
                )
            ],
        )
        assert len(result.audio_metric_results) == 1
        assert result.audio_metric_results[0].passed is False


class TestFormatTranscriptUseHeard:
    """Tests for use_heard parameter in judge format_transcript."""

    def test_metric_judge_format_without_heard(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge("test-model")
        transcript = [
            Message(
                role="assistant",
                content="Call 415-555-1234",
                metadata={"heard": "Call four fifteen five fifty five twelve thirty four"},
            ),
        ]
        result = judge._format_transcript(transcript)
        assert "415-555-1234" in result
        assert "four fifteen" not in result

    def test_metric_judge_format_with_heard(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge("test-model")
        transcript = [
            Message(
                role="assistant",
                content="Call 415-555-1234",
                metadata={"heard": "Call four fifteen five fifty five twelve thirty four"},
            ),
        ]
        result = judge._format_transcript(transcript, use_heard=True)
        assert "four fifteen" in result
        assert "415-555-1234" not in result

    def test_metric_judge_heard_only_for_assistant(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge("test-model")
        transcript = [
            Message(
                role="user",
                content="What is the number?",
                metadata={"heard": "should not be used"},
            ),
        ]
        result = judge._format_transcript(transcript, use_heard=True)
        assert "What is the number?" in result
        assert "should not be used" not in result

    def test_metric_judge_heard_fallback_to_content(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge("test-model")
        transcript = [
            Message(role="assistant", content="No heard metadata here"),
        ]
        result = judge._format_transcript(transcript, use_heard=True)
        assert "No heard metadata here" in result

    def test_rule_judge_format_with_heard(self):
        from voicetest.judges.rule import RuleJudge

        judge = RuleJudge()
        transcript = [
            Message(
                role="assistant",
                content="REF-ABC123",
                metadata={"heard": "ref abc one two three"},
            ),
        ]
        result = judge._format_transcript(transcript, use_heard=True)
        assert "ref abc one two three" in result
        assert "REF-ABC123" not in result

    def test_rule_judge_format_without_heard(self):
        from voicetest.judges.rule import RuleJudge

        judge = RuleJudge()
        transcript = [
            Message(
                role="assistant",
                content="REF-ABC123",
                metadata={"heard": "ref abc one two three"},
            ),
        ]
        result = judge._format_transcript(transcript)
        assert "REF-ABC123" in result
        assert "ref abc one two three" not in result
