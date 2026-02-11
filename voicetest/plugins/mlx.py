"""LiveKit plugin adapters for mlx-audio (macOS/Apple Silicon).

Provides STT (Whisper) and TTS (Kokoro) implementations that run on Metal.

Requires the 'macos' optional dependency group:
    uv sync --extra macos
"""

import asyncio
from dataclasses import dataclass
import tempfile
import uuid
import wave

from livekit import rtc
from livekit.agents import APIConnectOptions
from livekit.agents import stt
from livekit.agents import tts
from livekit.agents import utils
from mlx_audio.stt.generate import generate_transcription
from mlx_audio.tts.utils import load_model
import numpy as np


_DEFAULT_CONN_OPTIONS = APIConnectOptions()


@dataclass
class MlxSTTCapabilities:
    streaming: bool = False
    interim_results: bool = False


@dataclass
class MlxTTSCapabilities:
    streaming: bool = True


class MlxWhisperSTT(stt.STT):
    """Speech-to-text using Whisper via mlx-audio.

    Runs on Apple Silicon with Metal acceleration.
    """

    def __init__(
        self,
        *,
        model: str = "mlx-community/whisper-large-v3-turbo-asr-fp16",
        language: str = "en",
    ):
        super().__init__(
            capabilities=MlxSTTCapabilities(),
        )
        self._model_name = model
        self._language = language

    @property
    def label(self) -> str:
        return "mlx-whisper"

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: str | None = None,
        conn_options: APIConnectOptions = _DEFAULT_CONN_OPTIONS,
    ) -> stt.SpeechEvent:
        """Transcribe audio buffer using Whisper."""

        # Convert AudioBuffer to WAV file for mlx-audio
        frames = list(buffer)
        if not frames:
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                request_id=str(uuid.uuid4()),
                alternatives=[
                    stt.SpeechData(
                        language=language or self._language,
                        text="",
                        start_time=0.0,
                        end_time=0.0,
                        confidence=0.0,
                    )
                ],
            )

        # Combine frames into single audio buffer
        sample_rate = frames[0].sample_rate
        num_channels = frames[0].num_channels
        samples_per_channel = sum(f.samples_per_channel for f in frames)

        combined = rtc.AudioFrame(
            data=b"".join(f.data for f in frames),
            sample_rate=sample_rate,
            num_channels=num_channels,
            samples_per_channel=samples_per_channel,
        )

        # Write to temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
            with wave.open(f, "wb") as wav:
                wav.setnchannels(num_channels)
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(sample_rate)
                wav.writeframes(combined.data)

        # Run transcription in executor to avoid blocking
        loop = asyncio.get_event_loop()
        model_name = self._model_name
        result = await loop.run_in_executor(
            None,
            lambda: generate_transcription(model=model_name, audio=wav_path),
        )

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            request_id=str(uuid.uuid4()),
            alternatives=[
                stt.SpeechData(
                    language=language or self._language,
                    text=result.text.strip(),
                    start_time=0.0,
                    end_time=0.0,
                    confidence=1.0,
                )
            ],
        )

    def stream(
        self,
        *,
        language: str | None = None,
        conn_options: APIConnectOptions | None = None,
    ) -> stt.RecognizeStream:
        """Whisper doesn't support streaming, use VAD + recognize instead."""
        raise NotImplementedError(
            "MlxWhisperSTT doesn't support streaming. "
            "Use VAD with StreamAdapter for turn-based recognition."
        )


class MlxKokoroTTS(tts.TTS):
    """Text-to-speech using Kokoro via mlx-audio.

    Runs on Apple Silicon with Metal acceleration.
    """

    def __init__(
        self,
        *,
        model: str = "mlx-community/Kokoro-82M-bf16",
        voice: str = "af_heart",
        speed: float = 1.0,
        lang_code: str = "a",
    ):
        super().__init__(
            capabilities=MlxTTSCapabilities(),
            sample_rate=24000,
            num_channels=1,
        )
        self._model_name = model
        self._voice = voice
        self._speed = speed
        self._lang_code = lang_code
        self._model = None

    @property
    def label(self) -> str:
        return "mlx-kokoro"

    def _ensure_model(self):
        if self._model is None:
            self._model = load_model(self._model_name)

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions | None = None,
    ) -> tts.ChunkedStream:
        """Synthesize speech from text."""
        self._ensure_model()
        return MlxKokoroChunkedStream(
            tts=self,
            text=text,
            model=self._model,
            voice=self._voice,
            speed=self._speed,
            lang_code=self._lang_code,
        )

    def stream(
        self,
        *,
        conn_options: APIConnectOptions | None = None,
    ) -> tts.SynthesizeStream:
        """Return a streaming synthesis interface."""
        self._ensure_model()
        return MlxKokoroSynthesizeStream(
            tts=self,
            model=self._model,
            voice=self._voice,
            speed=self._speed,
            lang_code=self._lang_code,
        )


class MlxKokoroChunkedStream(tts.ChunkedStream):
    """Chunked stream for Kokoro TTS synthesis."""

    def __init__(
        self,
        *,
        tts: MlxKokoroTTS,
        text: str,
        model,
        voice: str,
        speed: float,
        lang_code: str,
        conn_options: APIConnectOptions = _DEFAULT_CONN_OPTIONS,
    ):
        super().__init__(tts=tts, input_text=text, conn_options=conn_options)
        self._model = model
        self._voice = voice
        self._speed = speed
        self._lang_code = lang_code
        self._request_id = str(uuid.uuid4())

    async def _run(self) -> None:
        """Generate audio chunks from text."""
        loop = asyncio.get_event_loop()

        model = self._model
        input_text = self.input_text
        voice = self._voice
        speed = self._speed
        lang_code = self._lang_code

        def generate():
            results = []
            for result in model.generate(
                text=input_text,
                voice=voice,
                speed=speed,
                lang_code=lang_code,
            ):
                audio_np = np.array(result.audio)
                audio_int16 = (audio_np * 32767).astype(np.int16)
                results.append(audio_int16.tobytes())
            return results

        audio_chunks = await loop.run_in_executor(None, generate)

        segment_id = str(uuid.uuid4())
        for i, chunk_data in enumerate(audio_chunks):
            is_final = i == len(audio_chunks) - 1
            frame = rtc.AudioFrame(
                data=chunk_data,
                sample_rate=24000,
                num_channels=1,
                samples_per_channel=len(chunk_data) // 2,
            )
            self._event_ch.send_nowait(
                tts.SynthesizedAudio(
                    frame=frame,
                    request_id=self._request_id,
                    is_final=is_final,
                    segment_id=segment_id,
                    delta_text=self.input_text if is_final else "",
                )
            )


class MlxKokoroSynthesizeStream(tts.SynthesizeStream):
    """Streaming synthesis interface for Kokoro TTS."""

    def __init__(
        self,
        *,
        tts: MlxKokoroTTS,
        model,
        voice: str,
        speed: float,
        lang_code: str,
        conn_options: APIConnectOptions = _DEFAULT_CONN_OPTIONS,
    ):
        super().__init__(tts=tts, conn_options=conn_options)
        self._model = model
        self._voice = voice
        self._speed = speed
        self._lang_code = lang_code

    async def _run(self) -> None:
        """Process incoming text and generate audio."""
        loop = asyncio.get_event_loop()

        async for input_data in self._input_ch:
            if isinstance(input_data, str):
                text = input_data
            elif hasattr(input_data, "text"):
                text = input_data.text
            else:
                continue

            if not text.strip():
                continue

            request_id = str(uuid.uuid4())
            segment_id = str(uuid.uuid4())

            def generate(
                model=self._model,
                text_to_speak=text,
                voice=self._voice,
                speed=self._speed,
                lang_code=self._lang_code,
            ):
                results = []
                for result in model.generate(
                    text=text_to_speak,
                    voice=voice,
                    speed=speed,
                    lang_code=lang_code,
                ):
                    audio_np = np.array(result.audio)
                    audio_int16 = (audio_np * 32767).astype(np.int16)
                    results.append(audio_int16.tobytes())
                return results

            audio_chunks = await loop.run_in_executor(None, generate)

            for i, chunk_data in enumerate(audio_chunks):
                is_final = i == len(audio_chunks) - 1
                frame = rtc.AudioFrame(
                    data=chunk_data,
                    sample_rate=24000,
                    num_channels=1,
                    samples_per_channel=len(chunk_data) // 2,
                )
                self._event_ch.send_nowait(
                    tts.SynthesizedAudio(
                        frame=frame,
                        request_id=request_id,
                        is_final=is_final,
                        segment_id=segment_id,
                        delta_text=text if is_final else "",
                    )
                )
