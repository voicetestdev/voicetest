/**
 * E2E tests for live voice calls.
 *
 * Tests the call UI flow: starting a call, viewing transcript, ending a call.
 * The "agent responds" test uses Chromium fake audio capture with a TTS-generated
 * WAV file to send speech through the full pipeline.
 *
 * Prerequisites for the agent response test:
 *   docker compose -f docker-compose.dev.yml up -d
 *   docker compose -f docker-compose.dev.yml exec backend claude login
 *
 * Run with:
 *   cd web && mise exec -- bunx playwright test live-call.e2e.ts --config=e2e/playwright.config.ts
 */

import { test, expect, chromium } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const KOKORO_URL = "http://localhost:8002";

// Check if LiveKit is available before running tests
async function isLiveKitAvailable(baseURL: string): Promise<boolean> {
  try {
    const response = await fetch(`${baseURL}/api/livekit/status`);
    if (!response.ok) return false;
    const data = await response.json();
    return data.available === true;
  } catch {
    return false;
  }
}

// Check if Kokoro TTS is available (needed for audio generation)
async function isKokoroAvailable(): Promise<boolean> {
  try {
    const response = await fetch(`${KOKORO_URL}/v1/models`, {
      signal: AbortSignal.timeout(5000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

// Generate a WAV file with speech followed by silence via Kokoro TTS.
// The silence gap lets the VAD detect end-of-speech and trigger STT
// with just the short utterance instead of buffering until max_buffered_speech.
async function generateSpeechWav(text: string, silenceSeconds = 4): Promise<string> {
  const response = await fetch(`${KOKORO_URL}/v1/audio/speech`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      input: text,
      model: "kokoro",
      voice: "af_heart",
      response_format: "wav",
    }),
  });

  if (!response.ok) {
    throw new Error(`Kokoro TTS failed: ${response.status} ${response.statusText}`);
  }

  const wavBuffer = Buffer.from(await response.arrayBuffer());

  // Parse WAV header to get audio format info
  const sampleRate = wavBuffer.readUInt32LE(24);
  const bitsPerSample = wavBuffer.readUInt16LE(34);
  const numChannels = wavBuffer.readUInt16LE(22);

  // Find the 'data' chunk to get the audio data offset and size
  let dataOffset = 12; // skip RIFF header
  while (dataOffset < wavBuffer.length - 8) {
    const chunkId = wavBuffer.toString("ascii", dataOffset, dataOffset + 4);
    if (chunkId === "data") break;
    const chunkSize = wavBuffer.readUInt32LE(dataOffset + 4);
    dataOffset += 8 + chunkSize;
  }
  const audioDataStart = dataOffset + 8;
  // Kokoro streams WAVs with size=0xFFFFFFFF; compute real size from file length
  const rawDataSize = wavBuffer.readUInt32LE(dataOffset + 4);
  const originalDataSize = rawDataSize === 0xFFFFFFFF
    ? wavBuffer.length - audioDataStart
    : rawDataSize;

  // Generate silence: zero-filled PCM samples
  const bytesPerSample = bitsPerSample / 8;
  const silenceBytes = sampleRate * numChannels * bytesPerSample * silenceSeconds;
  const silence = Buffer.alloc(silenceBytes, 0);

  // Build new WAV: original header chunks + original audio + silence
  const headerChunks = wavBuffer.subarray(0, audioDataStart);
  const audioData = wavBuffer.subarray(audioDataStart, audioDataStart + originalDataSize);

  const newDataSize = originalDataSize + silenceBytes;
  const newFileSize = audioDataStart + newDataSize;

  const result = Buffer.alloc(newFileSize);
  headerChunks.copy(result, 0);
  audioData.copy(result, audioDataStart);
  silence.copy(result, audioDataStart + originalDataSize);

  // Update RIFF chunk size (file size - 8)
  result.writeUInt32LE(newFileSize - 8, 4);
  // Update data chunk size
  result.writeUInt32LE(newDataSize, dataOffset + 4);

  const tmpFile = path.join(os.tmpdir(), `voicetest-hello-${Date.now()}.wav`);
  fs.writeFileSync(tmpFile, result);
  return tmpFile;
}

// Helper to select the first agent in the sidebar
async function selectAgent(page: import("@playwright/test").Page) {
  await page.goto("/");

  // Agents are buttons inside ul.agent-list > li
  const agentBtn = page.locator(".agent-list .agent-btn").first();
  await expect(agentBtn).toBeVisible({ timeout: 10000 });
  await agentBtn.click();

  // Wait for agent view to load
  await expect(page.locator("text=Export Agent")).toBeVisible({ timeout: 10000 });
}

// End any active call and disconnect cleanly.
// Called in afterEach to prevent state leaking between tests.
async function cleanupCall(page: import("@playwright/test").Page) {
  try {
    const endBtn = page.locator("button:has-text('End')");
    if (await endBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await endBtn.click({ force: true, timeout: 2000 }).catch(() => {});
      // Wait for call panel to disappear
      await page.locator(".call-panel").waitFor({ state: "hidden", timeout: 3000 }).catch(() => {});
    }
  } catch {
    // Ignore cleanup errors
  }
  // Navigate away to disconnect any WebRTC/WebSocket connections
  await page.goto("about:blank").catch(() => {});
  // Brief delay for LiveKit room cleanup between tests
  await new Promise((r) => setTimeout(r, 1000));
}

test.describe("Live Voice Calls", () => {
  test.setTimeout(60000);

  test.beforeEach(async ({ page, baseURL }) => {
    const available = await isLiveKitAvailable(baseURL || "http://localhost:8000");
    test.skip(!available, "LiveKit server not available");

    await page.context().grantPermissions(["microphone"]);
  });

  test.afterEach(async ({ page }) => {
    await cleanupCall(page);
  });

  test("Talk button shows LiveKit status", async ({ page }) => {
    await selectAgent(page);
    await expect(page.getByRole("button", { name: "Talk to Agent" })).toBeVisible({ timeout: 10000 });
  });

  test("starting a call shows call panel", async ({ page }) => {
    await selectAgent(page);

    const talkButton = page.getByRole("button", { name: "Talk to Agent" });
    await expect(talkButton).toBeVisible({ timeout: 10000 });
    await expect(talkButton).toBeEnabled();
    await talkButton.click();

    // Wait for call panel or error - "Connecting" state may be too brief to catch
    const callPanel = page.locator(".call-panel");
    const errorText = page.locator(".error-text");
    await expect(callPanel.or(errorText)).toBeVisible({ timeout: 15000 });

    // Verify we got the call panel, not an error
    if (await errorText.isVisible()) {
      const err = await errorText.textContent();
      throw new Error(`Call failed: ${err}`);
    }

    await expect(page.locator("text=Live Call")).toBeVisible();
    await expect(page.locator("button:has-text('Mute')")).toBeVisible();
    await expect(page.locator("button:has-text('End')")).toBeVisible();
    // Cleanup handled by afterEach
  });

  test("ending a call closes the call panel", async ({ page }) => {
    await selectAgent(page);

    const talkButton = page.getByRole("button", { name: "Talk to Agent" });
    await expect(talkButton).toBeVisible({ timeout: 10000 });
    await talkButton.click();

    await expect(page.locator(".call-panel")).toBeVisible({ timeout: 15000 });

    await page.locator("button:has-text('End')").click();
    // After ending, the save-run feature may navigate to runs view,
    // so just verify the call panel disappears.
    await expect(page.locator(".call-panel")).not.toBeVisible({ timeout: 5000 });
  });

  test("mute button toggles mute state", async ({ page }) => {
    await selectAgent(page);

    await page.getByRole("button", { name: "Talk to Agent" }).click();
    await expect(page.locator(".call-panel")).toBeVisible({ timeout: 15000 });

    // Re-query the button for each assertion to handle DOM updates
    await expect(page.locator(".call-controls button").first()).toHaveText("Mute", { timeout: 5000 });

    await page.locator(".call-controls button").first().click();
    await expect(page.locator(".call-controls button").first()).toHaveText("Unmute", { timeout: 5000 });

    await page.locator(".call-controls button").first().click();
    await expect(page.locator(".call-controls button").first()).toHaveText("Mute", { timeout: 5000 });
    // Cleanup handled by afterEach
  });

  test("transcript updates appear in call panel", async ({ page }) => {
    await selectAgent(page);

    await page.getByRole("button", { name: "Talk to Agent" }).click();
    await expect(page.locator(".call-panel")).toBeVisible({ timeout: 15000 });

    await expect(page.locator(".transcript")).toBeVisible();
    await expect(page.locator("text=Start speaking")).toBeVisible();
    // Cleanup handled by afterEach
  });
});

test.describe("Live Call Agent Response", () => {
  test.setTimeout(120000);

  let wavFile: string;

  test.beforeAll(async () => {
    const kokoroUp = await isKokoroAvailable();
    if (!kokoroUp) {
      return;
    }

    // Generate speech audio via Kokoro
    wavFile = await generateSpeechWav("Hello, how are you doing today?");
  });

  test.afterAll(async () => {
    if (wavFile && fs.existsSync(wavFile)) {
      fs.unlinkSync(wavFile);
    }
  });

  test("agent responds to speech", async ({ baseURL }) => {
    const available = await isLiveKitAvailable(baseURL || "http://localhost:8000");
    test.skip(!available, "LiveKit server not available");
    test.skip(!wavFile, "Kokoro TTS not available — cannot generate speech audio");

    // Launch a separate browser with fake audio device.
    // Chromium plays the WAV on loop as the microphone input.
    const browser = await chromium.launch({
      args: [
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        `--use-file-for-fake-audio-capture=${wavFile}`,
        "--autoplay-policy=no-user-gesture-required",
      ],
    });

    const context = await browser.newContext({
      permissions: ["microphone"],
      baseURL: baseURL || "http://localhost:8000",
    });

    const page = await context.newPage();

    // Forward browser console for debugging
    page.on("console", (msg) => {
      if (msg.type() === "error" || msg.type() === "warning") {
        console.log(`[browser ${msg.type()}] ${msg.text()}`);
      }
    });

    try {
      await selectAgent(page);

      // Start the call
      const talkButton = page.getByRole("button", { name: "Talk to Agent" });
      await expect(talkButton).toBeVisible({ timeout: 10000 });
      await talkButton.click();

      // Wait for call to be active (not error state)
      const callPanel = page.locator(".call-panel");
      const errorText = page.locator(".error-text");

      // Race between call becoming active and error state
      await expect(callPanel.or(errorText)).toBeVisible({ timeout: 15000 });

      // If error state, fail with the actual error message
      if (await errorText.isVisible()) {
        const errMsg = await errorText.textContent();
        throw new Error(`Call failed with error: ${errMsg}`);
      }

      // Wait for an agent message to appear in the transcript.
      // The fake audio feeds "Hello, how are you doing today?" → STT → LLM → response.
      // The Svelte template uses class:agent={msg.role === "assistant"}
      const agentMessage = page.locator(".transcript .message.agent");

      // Poll for agent message, but also check for error state during wait
      await expect(agentMessage.first().or(errorText)).toBeVisible({ timeout: 90000 });

      if (await errorText.isVisible()) {
        const errMsg = await errorText.textContent();
        throw new Error(`Call errored during conversation: ${errMsg}`);
      }

      // Verify the agent actually said something
      const text = await agentMessage.first().textContent();
      expect(text).toBeTruthy();
      expect(text!.length).toBeGreaterThan(0);

      // End the call
      await page.locator("button:has-text('End')").click();
      await expect(page.locator(".call-panel")).not.toBeVisible({ timeout: 5000 });
    } finally {
      await context.close();
      await browser.close();
    }
  });
});
