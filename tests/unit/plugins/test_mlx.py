"""Tests for MLX audio plugins (macOS/Apple Silicon).

These tests require the 'macos' optional dependency group:
    uv sync --extra macos
"""

import pytest


# Skip all tests if mlx native library is not available (requires Apple Silicon)
pytest.importorskip("mlx.core", reason="mlx requires Apple Silicon (libmlx.so not available)")


class TestMlxWhisperSTT:
    """Tests for MlxWhisperSTT speech-to-text."""

    def test_import(self):
        """Test that MlxWhisperSTT can be imported."""
        from voicetest.plugins.mlx import MlxWhisperSTT

        assert MlxWhisperSTT is not None

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        from voicetest.plugins.mlx import MlxWhisperSTT

        stt = MlxWhisperSTT()

        assert stt._model_name == "mlx-community/whisper-large-v3-turbo-asr-fp16"
        assert stt._language == "en"
        assert stt.label == "mlx-whisper"

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        from voicetest.plugins.mlx import MlxWhisperSTT

        stt = MlxWhisperSTT(
            model="custom-whisper-model",
            language="fr",
        )

        assert stt._model_name == "custom-whisper-model"
        assert stt._language == "fr"

    def test_capabilities(self):
        """Test that capabilities are correctly set."""
        from voicetest.plugins.mlx import MlxWhisperSTT

        stt = MlxWhisperSTT()

        assert stt.capabilities.streaming is False
        assert stt.capabilities.interim_results is False

    def test_stream_not_supported(self):
        """Test that streaming is not supported."""
        from voicetest.plugins.mlx import MlxWhisperSTT

        stt = MlxWhisperSTT()

        with pytest.raises(NotImplementedError, match="doesn't support streaming"):
            stt.stream()


class TestMlxKokoroTTS:
    """Tests for MlxKokoroTTS text-to-speech."""

    def test_import(self):
        """Test that MlxKokoroTTS can be imported."""
        from voicetest.plugins.mlx import MlxKokoroTTS

        assert MlxKokoroTTS is not None

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        from voicetest.plugins.mlx import MlxKokoroTTS

        tts = MlxKokoroTTS()

        assert tts._model_name == "mlx-community/Kokoro-82M-bf16"
        assert tts._voice == "af_heart"
        assert tts._speed == 1.0
        assert tts._lang_code == "a"
        assert tts.label == "mlx-kokoro"

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        from voicetest.plugins.mlx import MlxKokoroTTS

        tts = MlxKokoroTTS(
            model="custom-kokoro-model",
            voice="bm_daniel",
            speed=1.2,
            lang_code="b",
        )

        assert tts._model_name == "custom-kokoro-model"
        assert tts._voice == "bm_daniel"
        assert tts._speed == 1.2
        assert tts._lang_code == "b"

    def test_capabilities(self):
        """Test that capabilities are correctly set."""
        from voicetest.plugins.mlx import MlxKokoroTTS

        tts = MlxKokoroTTS()

        assert tts.capabilities.streaming is True

    def test_sample_rate(self):
        """Test that sample rate is set correctly."""
        from voicetest.plugins.mlx import MlxKokoroTTS

        tts = MlxKokoroTTS()

        assert tts.sample_rate == 24000
        assert tts.num_channels == 1


class TestMlxPluginsIntegration:
    """Integration tests requiring model loading (slower)."""

    @pytest.mark.slow
    def test_tts_synthesize_returns_chunked_stream(self):
        """Test that synthesize returns a ChunkedStream."""
        from livekit.agents import tts

        from voicetest.plugins.mlx import MlxKokoroTTS

        tts_instance = MlxKokoroTTS()
        stream = tts_instance.synthesize("Hello, world!")

        assert isinstance(stream, tts.ChunkedStream)

    @pytest.mark.slow
    def test_tts_stream_returns_synthesize_stream(self):
        """Test that stream returns a SynthesizeStream."""
        from livekit.agents import tts

        from voicetest.plugins.mlx import MlxKokoroTTS

        tts_instance = MlxKokoroTTS()
        stream = tts_instance.stream()

        assert isinstance(stream, tts.SynthesizeStream)
