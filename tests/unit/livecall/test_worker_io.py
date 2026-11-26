import argparse

from voicetest.livecall.worker_io import add_voice_args
from voicetest.livecall.worker_io import build_stt
from voicetest.livecall.worker_io import build_tts
from voicetest.settings import AudioSettings


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_voice_args(parser)
    return parser.parse_args(argv)


class TestVoiceArgs:
    def test_audio_settings_default_to_settings_defaults(self, monkeypatch):
        monkeypatch.delenv("WHISPER_URL", raising=False)
        monkeypatch.delenv("KOKORO_URL", raising=False)

        assert _parse([]).audio_settings == AudioSettings()

    def test_audio_settings_parsed_from_json(self):
        audio = AudioSettings(stt_url="http://stt/v1", tts_url="http://tts/v1", voice="v")

        args = _parse(["--audio-settings", audio.model_dump_json()])

        assert args.audio_settings == audio


class TestLocalBackend:
    def test_stt_and_tts_use_audio_settings(self):
        audio = AudioSettings(
            stt_url="http://stt/v1",
            tts_url="http://tts/v1",
            stt_model="stt-model",
            tts_model="tts-model",
            voice="voice-x",
        )
        args = _parse(["--backend", "local", "--audio-settings", audio.model_dump_json()])

        stt = build_stt(args)
        tts = build_tts(args)

        assert stt._opts.model == "stt-model"
        assert str(stt._client.base_url).rstrip("/") == "http://stt/v1"
        assert tts._opts.model == "tts-model"
        assert tts._opts.voice == "voice-x"
        assert str(tts._client.base_url).rstrip("/") == "http://tts/v1"
