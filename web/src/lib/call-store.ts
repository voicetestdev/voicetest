/**
 * Svelte store for live call state management.
 */

import { writable, get } from "svelte/store";
import { api } from "./api";
import { connectToRoom, cleanupAudioElements, type LiveKitConnection } from "./livekit";
import { loadRunHistory, selectRun } from "./stores";
import type { CallTranscriptMessage, CallStatus } from "./types";

export interface CallState {
  callId: string | null;
  status: CallStatus | "idle";
  transcript: CallTranscriptMessage[];
  error: string | null;
  muted: boolean;
}

export interface LiveKitStatus {
  available: boolean;
  error: string | null;
  checking: boolean;
}

const initialState: CallState = {
  callId: null,
  status: "idle",
  transcript: [],
  error: null,
  muted: false,
};

const initialLiveKitStatus: LiveKitStatus = {
  available: false,
  error: null,
  checking: true,
};

export const callState = writable<CallState>(initialState);
export const callWebSocket = writable<WebSocket | null>(null);
export const liveKitStatus = writable<LiveKitStatus>(initialLiveKitStatus);

let livekitConnection: LiveKitConnection | null = null;

export async function startCall(agentId: string): Promise<void> {
  callState.set({
    ...initialState,
    status: "connecting",
  });

  try {
    const response = await api.startCall(agentId);

    callState.update((s) => ({
      ...s,
      callId: response.call_id,
    }));

    connectCallWebSocket(response.call_id);

    livekitConnection = await connectToRoom(response.livekit_url, response.token, {
      onConnected: () => {
        callState.update((s) => ({ ...s, status: "active" }));
      },
      onDisconnected: () => {
        callState.update((s) => ({ ...s, status: "ended" }));
        cleanupCall();
      },
      onError: (error) => {
        callState.update((s) => ({
          ...s,
          status: "error",
          error: error.message,
        }));
      },
      onConnectionStateChanged: (state) => {
        if (state === "disconnected") {
          callState.update((s) => ({ ...s, status: "ended" }));
        }
      },
    });
  } catch (error) {
    callState.update((s) => ({
      ...s,
      status: "error",
      error: error instanceof Error ? error.message : String(error),
    }));
  }
}

export async function endCall(agentId: string): Promise<void> {
  const state = get(callState);
  if (!state.callId) return;

  let runId: string | null = null;

  try {
    const response = await api.endCall(state.callId);
    runId = response.run_id;
  } catch (error) {
    console.error("Error ending call:", error);
  }

  cleanupCall();

  if (runId && agentId) {
    await loadRunHistory(agentId);
    await selectRun(agentId, runId);
  }
}

export async function toggleMute(): Promise<void> {
  const state = get(callState);
  const newMuted = !state.muted;

  if (livekitConnection) {
    try {
      await livekitConnection.setMuted(newMuted);
    } catch (error) {
      console.warn("Failed to toggle microphone:", error);
    }
  }
  callState.update((s) => ({ ...s, muted: newMuted }));
}

function connectCallWebSocket(callId: string): void {
  disconnectCallWebSocket();

  const wsUrl = api.getWebSocketUrl(`/calls/${callId}/ws`);
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }

    if (data.type === "state" && data.call) {
      callState.update((s) => ({
        ...s,
        status: data.call.status as CallStatus,
        transcript: data.call.transcript || [],
      }));
    } else if (data.type === "transcript_update") {
      callState.update((s) => ({
        ...s,
        transcript: data.transcript || [],
      }));
    } else if (data.type === "call_ended") {
      callState.update((s) => ({ ...s, status: "ended" }));
      cleanupCall();
    } else if (data.type === "error") {
      callState.update((s) => ({
        ...s,
        status: "error",
        error: data.message,
      }));
    }
  };

  ws.onclose = () => {
    callWebSocket.set(null);
  };

  callWebSocket.set(ws);
}

function disconnectCallWebSocket(): void {
  const ws = get(callWebSocket);
  if (ws) {
    ws.close();
    callWebSocket.set(null);
  }
}

function cleanupCall(): void {
  disconnectCallWebSocket();

  if (livekitConnection) {
    livekitConnection.disconnect().catch(console.error);
    livekitConnection = null;
  }

  cleanupAudioElements();

  callState.set(initialState);
}

export function resetCallState(): void {
  cleanupCall();
}

export async function checkLiveKitStatus(retries = 3, delayMs = 1000): Promise<void> {
  liveKitStatus.update((s) => ({ ...s, checking: true }));

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const status = await api.getLiveKitStatus();
      if (status.available) {
        liveKitStatus.set({
          available: true,
          error: null,
          checking: false,
        });
        return;
      }
      // Not available, but no exception - might be starting up
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
        continue;
      }
      liveKitStatus.set({
        available: false,
        error: status.error,
        checking: false,
      });
    } catch (error) {
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
        continue;
      }
      liveKitStatus.set({
        available: false,
        error: error instanceof Error ? error.message : "Failed to check LiveKit status",
        checking: false,
      });
    }
  }
}
