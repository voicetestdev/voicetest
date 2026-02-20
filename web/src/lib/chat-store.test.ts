import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import { chatState, resetChatState } from "./chat-store";

describe("chat-store", () => {
  beforeEach(() => {
    resetChatState();
  });

  afterEach(() => {
    resetChatState();
  });

  describe("initial state", () => {
    it("should start with idle status", () => {
      const state = get(chatState);
      expect(state.status).toBe("idle");
      expect(state.chatId).toBeNull();
      expect(state.transcript).toEqual([]);
      expect(state.error).toBeNull();
      expect(state.streaming).toBe(false);
      expect(state.streamingContent).toBe("");
    });
  });

  describe("resetChatState", () => {
    it("should reset to initial state", () => {
      chatState.update((s) => ({
        ...s,
        chatId: "test-id",
        status: "active",
        transcript: [{ role: "user", content: "hello" }],
      }));

      resetChatState();

      const state = get(chatState);
      expect(state.status).toBe("idle");
      expect(state.chatId).toBeNull();
      expect(state.transcript).toEqual([]);
    });
  });

  describe("chatState store", () => {
    it("should support streaming state updates", () => {
      chatState.update((s) => ({
        ...s,
        streaming: true,
        streamingContent: "Hello ",
      }));

      let state = get(chatState);
      expect(state.streaming).toBe(true);
      expect(state.streamingContent).toBe("Hello ");

      chatState.update((s) => ({
        ...s,
        streamingContent: s.streamingContent + "world",
      }));

      state = get(chatState);
      expect(state.streamingContent).toBe("Hello world");
    });

    it("should support transcript updates", () => {
      chatState.update((s) => ({
        ...s,
        transcript: [
          { role: "user" as const, content: "hi" },
          { role: "assistant" as const, content: "hello" },
        ],
      }));

      const state = get(chatState);
      expect(state.transcript).toHaveLength(2);
      expect(state.transcript[0].role).toBe("user");
      expect(state.transcript[1].role).toBe("assistant");
    });

    it("should support error state", () => {
      chatState.update((s) => ({
        ...s,
        status: "error" as const,
        error: "Connection failed",
      }));

      const state = get(chatState);
      expect(state.status).toBe("error");
      expect(state.error).toBe("Connection failed");
    });
  });
});
