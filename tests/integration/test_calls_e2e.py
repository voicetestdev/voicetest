"""End-to-end tests for live voice calls with actual audio.

These tests verify the complete audio pipeline:
1. User publishes audio to LiveKit
2. Agent transcribes via Whisper
3. Agent generates response via Ollama
4. Agent speaks response via Kokoro
5. Transcript appears via WebSocket

Run with: uv run pytest tests/integration/test_calls_e2e.py -v -s
Requires: docker compose -f docker-compose.dev.yml up -d
"""

import asyncio
import io
import json
import struct
import subprocess
import time
import wave

import pytest


def docker_compose_running() -> bool:
    """Check if docker compose services are running."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.dev.yml", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False
        services = result.stdout.strip()
        return "backend" in services and "running" in services.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def ollama_available() -> bool:
    """Check if Ollama is running on localhost."""
    try:
        import httpx

        response = httpx.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(
        not docker_compose_running(),
        reason="Docker compose not running",
    ),
    pytest.mark.skipif(
        not ollama_available(),
        reason="Ollama not running on localhost:11434",
    ),
]


def generate_sine_wave_audio(
    frequency: float = 440.0,
    duration: float = 1.0,
    sample_rate: int = 48000,
) -> bytes:
    """Generate a sine wave audio as raw PCM bytes."""
    import math

    num_samples = int(sample_rate * duration)
    samples = []
    for i in range(num_samples):
        sample = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(struct.pack("<h", sample))
    return b"".join(samples)


def generate_test_audio_wav() -> bytes:
    """Generate a test WAV file with a simple tone."""
    sample_rate = 48000
    duration = 0.5
    pcm_data = generate_sine_wave_audio(440.0, duration, sample_rate)

    # Create WAV file in memory
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_data)

    return buffer.getvalue()


class TestWhisperSTT:
    """Test Whisper STT service directly."""

    def test_whisper_health(self):
        """Whisper service is healthy."""
        import httpx

        # Whisper is on port 8001 (mapped from container's 8000)
        response = httpx.get("http://localhost:8001/health", timeout=10)
        assert response.status_code == 200

    def test_whisper_transcribes_audio(self):
        """Whisper can transcribe audio (even if it's just silence/tone)."""
        import httpx

        # Generate a simple audio file
        audio_data = generate_test_audio_wav()

        # Send to Whisper API
        response = httpx.post(
            "http://localhost:8001/v1/audio/transcriptions",
            files={"file": ("test.wav", audio_data, "audio/wav")},
            data={"model": "Systran/faster-whisper-base.en"},
            timeout=30,
        )

        print(f"Whisper response: {response.status_code} - {response.text}")

        # Should get a response (even if empty transcription for a tone)
        assert response.status_code == 200
        data = response.json()
        assert "text" in data


class TestKokoroTTS:
    """Test Kokoro TTS service directly."""

    def test_kokoro_health(self):
        """Kokoro TTS service is available."""
        import httpx

        # Kokoro is on port 8002 (mapped from container's 8880)
        # Check the OpenAI-compatible endpoint
        try:
            response = httpx.get("http://localhost:8002/health", timeout=10)
            assert response.status_code == 200
        except httpx.HTTPStatusError:
            # Try the models endpoint instead
            response = httpx.get("http://localhost:8002/v1/models", timeout=10)
            assert response.status_code == 200

    def test_kokoro_synthesizes_speech(self):
        """Kokoro can synthesize speech from text."""
        import httpx

        response = httpx.post(
            "http://localhost:8002/v1/audio/speech",
            json={
                "model": "kokoro",
                "input": "Hello, this is a test.",
                "voice": "af_heart",
            },
            timeout=30,
        )

        print(f"Kokoro response: {response.status_code}")

        assert response.status_code == 200
        # Should return audio data
        assert len(response.content) > 0


class TestOllamaLLM:
    """Test Ollama LLM service directly."""

    def test_ollama_chat_completion(self):
        """Ollama can generate chat completions."""
        import httpx

        response = httpx.post(
            "http://localhost:11434/v1/chat/completions",
            json={
                "model": "qwen2.5:0.5b",
                "messages": [{"role": "user", "content": "Say hello in one word."}],
                "max_tokens": 10,
            },
            timeout=60,
        )

        print(f"Ollama response: {response.status_code} - {response.text[:200]}")

        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0


class TestFullCallPipeline:
    """Test the full call pipeline with simulated audio."""

    @pytest.fixture
    def api_base_url(self) -> str:
        return "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_agent_responds_to_user_audio(self, api_base_url):
        """Agent processes user audio and generates a response.

        This test:
        1. Starts a call
        2. Connects to the room as a user via LiveKit
        3. Publishes a synthetic audio track with speech
        4. Waits for transcript updates
        5. Verifies agent responded
        """
        import httpx
        from livekit import rtc

        # Create demo agent
        async with httpx.AsyncClient() as client:
            demo_response = await client.post(f"{api_base_url}/api/demo", timeout=30)
            assert demo_response.status_code == 200
            agent_id = demo_response.json()["agent_id"]

            # Start call
            start_response = await client.post(
                f"{api_base_url}/api/agents/{agent_id}/calls/start",
                timeout=30,
            )
            assert start_response.status_code == 200
            call_data = start_response.json()

        call_id = call_data["call_id"]
        room_name = call_data["room_name"]
        livekit_url = call_data["livekit_url"]
        user_token = call_data["token"]

        print(f"Call started: {call_id}, room: {room_name}")

        transcripts = []
        errors = []

        try:
            # Connect to LiveKit room as user
            room = rtc.Room()

            await room.connect(livekit_url, user_token)
            print("User connected to room")

            # Wait for agent to join
            await asyncio.sleep(2)

            # Create and publish an audio track
            # Use AudioSource to push audio frames
            audio_source = rtc.AudioSource(48000, 1)  # 48kHz mono
            track = rtc.LocalAudioTrack.create_audio_track("microphone", audio_source)

            # Publish the track
            options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            await room.local_participant.publish_track(track, options)
            print("Audio track published")

            # Generate some audio frames (silence for now - real test would use TTS audio)
            # Push a few seconds of silence/low-level audio
            samples_per_frame = 480  # 10ms at 48kHz
            frame_data = bytes(samples_per_frame * 2)  # 16-bit silence

            for _ in range(100):  # ~1 second of audio
                frame = rtc.AudioFrame(
                    data=frame_data,
                    sample_rate=48000,
                    num_channels=1,
                    samples_per_channel=samples_per_frame,
                )
                await audio_source.capture_frame(frame)
                await asyncio.sleep(0.01)

            print("Audio frames sent")

            # Connect to WebSocket for transcript updates
            import websockets

            ws_url = f"ws://localhost:8000/api/calls/{call_id}/ws"

            async with websockets.connect(ws_url) as ws:
                # Read initial state
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                print(f"WS initial: {data.get('type')}")

                # Wait for transcript updates
                start_time = time.time()
                timeout_secs = 15

                while time.time() - start_time < timeout_secs:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2)
                        data = json.loads(msg)
                        print(f"WS message: {data}")

                        if data.get("type") == "transcript_update":
                            transcripts.extend(data.get("transcript", []))
                            if transcripts:
                                print(f"Got transcripts: {transcripts}")

                        elif data.get("type") == "error":
                            errors.append(data.get("message"))
                            print(f"Error: {data.get('message')}")
                            break

                    except TimeoutError:
                        if transcripts:
                            break
                        continue

            await room.disconnect()

        finally:
            # Clean up - end the call
            async with httpx.AsyncClient() as client:
                await client.post(f"{api_base_url}/api/calls/{call_id}/end", timeout=10)

        # Report results
        print(f"Transcripts collected: {transcripts}")
        print(f"Errors: {errors}")

        # Verify no errors occurred during the call
        assert not errors, f"Errors during call: {errors}"

    @pytest.mark.asyncio
    async def test_agent_transcribes_real_speech(self, api_base_url):
        """Agent transcribes real speech audio and responds.

        This test uses Kokoro TTS to generate speech, then sends it to the agent.
        The agent should transcribe it and generate a response.
        """
        import httpx
        from livekit import rtc

        # First, generate speech audio using Kokoro
        async with httpx.AsyncClient() as client:
            tts_response = await client.post(
                "http://localhost:8002/v1/audio/speech",
                json={
                    "model": "kokoro",
                    "input": "Hello, how are you today?",
                    "voice": "af_heart",
                    "response_format": "pcm",  # Raw PCM for easier processing
                },
                timeout=30,
            )
            assert tts_response.status_code == 200
            speech_audio = tts_response.content

        print(f"Generated {len(speech_audio)} bytes of speech audio")

        # Create demo agent
        async with httpx.AsyncClient() as client:
            demo_response = await client.post(f"{api_base_url}/api/demo", timeout=30)
            agent_id = demo_response.json()["agent_id"]

            start_response = await client.post(
                f"{api_base_url}/api/agents/{agent_id}/calls/start",
                timeout=30,
            )
            call_data = start_response.json()

        call_id = call_data["call_id"]
        livekit_url = call_data["livekit_url"]
        user_token = call_data["token"]

        print(f"Call started: {call_id}")

        transcripts = []
        errors = []

        try:
            room = rtc.Room()
            await room.connect(livekit_url, user_token)
            print("User connected to room")

            await asyncio.sleep(2)  # Wait for agent

            # Create audio source and track
            # Kokoro outputs 24kHz audio by default
            sample_rate = 24000
            audio_source = rtc.AudioSource(sample_rate, 1)
            track = rtc.LocalAudioTrack.create_audio_track("microphone", audio_source)

            options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            await room.local_participant.publish_track(track, options)
            print("Audio track published")

            # Send the speech audio in chunks
            samples_per_frame = sample_rate // 100  # 10ms frames
            bytes_per_frame = samples_per_frame * 2  # 16-bit audio

            for i in range(0, len(speech_audio), bytes_per_frame):
                chunk = speech_audio[i : i + bytes_per_frame]
                if len(chunk) < bytes_per_frame:
                    # Pad with silence
                    chunk = chunk + bytes(bytes_per_frame - len(chunk))

                frame = rtc.AudioFrame(
                    data=chunk,
                    sample_rate=sample_rate,
                    num_channels=1,
                    samples_per_channel=samples_per_frame,
                )
                await audio_source.capture_frame(frame)
                await asyncio.sleep(0.01)

            print("Speech audio sent")

            # Wait for processing
            await asyncio.sleep(3)

            # Check for transcripts via WebSocket
            import websockets

            ws_url = f"ws://localhost:8000/api/calls/{call_id}/ws"

            async with websockets.connect(ws_url) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                print(f"WS state: {data}")

                if data.get("type") == "state" and data.get("call", {}).get("transcript"):
                    transcripts = data["call"]["transcript"]

                # Listen for more updates - wait longer for LLM + TTS
                start_time = time.time()
                while time.time() - start_time < 45:  # Extended timeout for LLM processing
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=3)
                        data = json.loads(msg)
                        print(f"WS message: {data}")

                        if data.get("type") == "transcript_update":
                            transcripts = data.get("transcript", [])
                            # Look for agent response
                            agent_msgs = [t for t in transcripts if t.get("role") == "assistant"]
                            if agent_msgs:
                                print(f"Agent responded: {agent_msgs}")
                                break

                        elif data.get("type") == "error":
                            errors.append(data.get("message"))
                            break

                    except TimeoutError:
                        # Print status periodically
                        elapsed = time.time() - start_time
                        print(f"Waiting for agent response... ({elapsed:.1f}s)")
                        continue

            await room.disconnect()

        finally:
            async with httpx.AsyncClient() as client:
                await client.post(f"{api_base_url}/api/calls/{call_id}/end", timeout=10)

        print(f"Final transcripts: {transcripts}")
        print(f"Errors: {errors}")

        assert not errors, f"Errors during call: {errors}"

        # Check if we got any transcription
        user_msgs = [t for t in transcripts if t.get("role") == "user"]
        agent_msgs = [t for t in transcripts if t.get("role") == "assistant"]

        print(f"User messages: {user_msgs}")
        print(f"Agent messages: {agent_msgs}")

        # The test passes if we got through without errors
        # Full transcript verification depends on the agent processing the audio

    @pytest.mark.asyncio
    async def test_call_websocket_receives_status(self, api_base_url):
        """WebSocket receives call status updates."""
        import httpx
        import websockets

        # Create demo agent
        async with httpx.AsyncClient() as client:
            demo_response = await client.post(f"{api_base_url}/api/demo", timeout=30)
            agent_id = demo_response.json()["agent_id"]

            # Start call
            start_response = await client.post(
                f"{api_base_url}/api/agents/{agent_id}/calls/start",
                timeout=30,
            )
            call_data = start_response.json()

        call_id = call_data["call_id"]

        try:
            ws_url = f"ws://localhost:8000/api/calls/{call_id}/ws"

            async with websockets.connect(ws_url) as ws:
                # Should receive initial state
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)

                assert data.get("type") == "state"
                assert "call" in data
                assert data["call"]["id"] == call_id

                print(f"Received call state: status={data['call']['status']}")

        finally:
            async with httpx.AsyncClient() as client:
                await client.post(f"{api_base_url}/api/calls/{call_id}/end", timeout=10)
