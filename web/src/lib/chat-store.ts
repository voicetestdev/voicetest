/**
 * Svelte store for text chat state management.
 *
 * Provides a text-based live conversation with an agent via WebSocket.
 * No LiveKit or audio infrastructure required.
 */

import { writable, get } from "svelte/store";
import { api } from "./api";
import { loadRunHistory, selectRun } from "./stores";
import type { CallTranscriptMessage } from "./types";

export interface ChatState {
  chatId: string | null;
  status: "idle" | "connecting" | "active" | "ended" | "error";
  transcript: CallTranscriptMessage[];
  error: string | null;
  streaming: boolean;
  streamingContent: string;
}

const initialState: ChatState = {
  chatId: null,
  status: "idle",
  transcript: [],
  error: null,
  streaming: false,
  streamingContent: "",
};

export const chatState = writable<ChatState>(initialState);
export const chatWebSocket = writable<WebSocket | null>(null);

export async function startChat(agentId: string): Promise<void> {
  chatState.set({
    ...initialState,
    status: "connecting",
  });

  try {
    const response = await api.startChat(agentId);

    chatState.update((s) => ({
      ...s,
      chatId: response.chat_id,
      status: "active",
    }));

    connectChatWebSocket(response.chat_id);
  } catch (error) {
    chatState.update((s) => ({
      ...s,
      status: "error",
      error: error instanceof Error ? error.message : String(error),
    }));
  }
}

export function sendMessage(content: string): void {
  const ws = get(chatWebSocket);
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  ws.send(JSON.stringify({ type: "message", content }));

  // Set streaming state while waiting for agent response
  chatState.update((s) => ({
    ...s,
    streaming: true,
    streamingContent: "",
  }));
}

export async function endChat(agentId: string): Promise<void> {
  const state = get(chatState);
  if (!state.chatId) return;

  let runId: string | null = null;

  try {
    const response = await api.endChat(state.chatId);
    runId = response.run_id;
  } catch (error) {
    console.error("Error ending chat:", error);
  }

  cleanupChat();

  if (runId && agentId) {
    await loadRunHistory(agentId);
    await selectRun(agentId, runId);
  }
}

function connectChatWebSocket(chatId: string): void {
  disconnectChatWebSocket();

  const wsUrl = api.getWebSocketUrl(`/chats/${chatId}/ws`);
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }

    if (data.type === "state" && data.chat) {
      chatState.update((s) => ({
        ...s,
        status: data.chat.status === "active" ? "active" : s.status,
        transcript: data.chat.transcript || [],
      }));
    } else if (data.type === "transcript_update") {
      chatState.update((s) => ({
        ...s,
        transcript: data.transcript || [],
        streaming: false,
        streamingContent: "",
      }));
    } else if (data.type === "token") {
      chatState.update((s) => ({
        ...s,
        streaming: true,
        streamingContent: s.streamingContent + (data.content || ""),
      }));
    } else if (data.type === "chat_ended") {
      chatState.update((s) => ({
        ...s,
        status: "ended",
        streaming: false,
        streamingContent: "",
      }));
      disconnectChatWebSocket();
    } else if (data.type === "error") {
      chatState.update((s) => ({
        ...s,
        status: "error",
        error: data.message,
        streaming: false,
        streamingContent: "",
      }));
    }
  };

  ws.onclose = () => {
    chatWebSocket.set(null);
  };

  chatWebSocket.set(ws);
}

function disconnectChatWebSocket(): void {
  const ws = get(chatWebSocket);
  if (ws) {
    ws.close();
    chatWebSocket.set(null);
  }
}

function cleanupChat(): void {
  disconnectChatWebSocket();
  chatState.set(initialState);
}

export function dismissChat(): void {
  chatState.set(initialState);
}

export function resetChatState(): void {
  cleanupChat();
}
