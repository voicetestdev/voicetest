<script lang="ts">
  import { onDestroy, tick } from "svelte";
  import { currentAgentId } from "../lib/stores";
  import {
    chatState,
    startChat,
    endChat,
    sendMessage,
    dismissChat,
    resetChatState,
  } from "../lib/chat-store";

  let chat = $derived($chatState);
  let agentId = $derived($currentAgentId);

  let inputValue = $state("");
  let messagesContainer = $state<HTMLDivElement | undefined>(undefined);

  onDestroy(() => {
    resetChatState();
  });

  async function handleStartChat() {
    if (!agentId) return;
    await startChat(agentId);
  }

  async function handleEndChat() {
    if (!agentId) return;
    await endChat(agentId);
  }

  function handleSend() {
    const content = inputValue.trim();
    if (!content) return;
    sendMessage(content);
    inputValue = "";
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  $effect(() => {
    // Scroll to bottom when transcript or streaming content changes
    // Reading these properties establishes reactive tracking
    if (chat.transcript.length > 0 || chat.streamingContent) {
      if (messagesContainer) {
        const container = messagesContainer;
        tick().then(() => {
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        });
      }
    }
  });
</script>

<button
  class="btn-primary"
  class:connecting={chat.status === "connecting"}
  disabled={!agentId || chat.status === "connecting" || chat.status === "active" || chat.status === "ended"}
  onclick={handleStartChat}
>
  {#if chat.status === "connecting"}
    <span class="spinner"></span>
    Connecting...
  {:else}
    Chat with Agent
  {/if}
</button>

{#if chat.status === "active" || chat.status === "ended"}
  <div class="chat-panel">
    <div class="chat-header">
      {#if chat.status === "ended"}
        <span class="chat-status ended">Chat Ended</span>
        <div class="chat-controls">
          <button class="btn-sm" onclick={dismissChat}>
            Close
          </button>
        </div>
      {:else}
        <span class="chat-status">Live Chat</span>
        <div class="chat-controls">
          <button class="btn-sm btn-danger" onclick={handleEndChat}>
            End
          </button>
        </div>
      {/if}
    </div>
    <div class="transcript" bind:this={messagesContainer}>
      {#if chat.transcript.length === 0 && !chat.streaming}
        <p class="empty-state">Type a message to start...</p>
      {:else}
        <div class="messages">
          {#each chat.transcript as msg}
            <div class="message" class:user={msg.role === "user"} class:agent={msg.role === "assistant"}>
              <span class="role">{msg.role === "user" ? "You" : "Agent"}:</span>
              <span class="content">{msg.content}</span>
            </div>
          {/each}
          {#if chat.streaming && chat.streamingContent}
            <div class="message agent streaming">
              <span class="role">Agent:</span>
              <span class="content">{chat.streamingContent}<span class="cursor">|</span></span>
            </div>
          {/if}
        </div>
      {/if}
    </div>
    {#if chat.status === "active"}
      <div class="input-area">
        <input
          type="text"
          class="chat-input"
          bind:value={inputValue}
          onkeydown={handleKeydown}
          placeholder="Type a message..."
          disabled={chat.streaming}
        />
        <button
          class="btn-sm send-btn"
          onclick={handleSend}
          disabled={!inputValue.trim() || chat.streaming}
        >
          Send
        </button>
      </div>
    {/if}
  </div>
{/if}

{#if chat.status === "error"}
  <div class="error-inline">
    <span class="error-text">{chat.error || "Chat failed"}</span>
    <button class="btn-sm" onclick={handleStartChat}>Retry</button>
  </div>
{/if}

<style>
  .connecting {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid var(--border-color);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .chat-panel {
    position: fixed;
    bottom: 1rem;
    right: 1rem;
    width: 360px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 100;
    display: flex;
    flex-direction: column;
    max-height: 450px;
  }

  .chat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-3);
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-tertiary);
    border-radius: var(--radius-md) var(--radius-md) 0 0;
  }

  .chat-status {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--success-text);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .chat-status::before {
    content: "";
    width: 8px;
    height: 8px;
    background: var(--success-text);
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  .chat-status.ended {
    color: var(--text-secondary);
  }

  .chat-status.ended::before {
    background: var(--text-secondary);
    animation: none;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .chat-controls {
    display: flex;
    gap: 0.25rem;
  }

  .transcript {
    padding: var(--space-3);
    max-height: 300px;
    overflow-y: auto;
    flex: 1;
  }

  .messages {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .message {
    display: flex;
    gap: 0.4rem;
    font-size: 0.8rem;
  }

  .message .role {
    font-weight: 500;
    color: var(--text-secondary);
    min-width: 40px;
  }

  .message.user .role {
    color: var(--accent);
  }

  .message.agent .role {
    color: var(--success-text);
  }

  .message .content {
    color: var(--text-primary);
    flex: 1;
  }

  .message.streaming {
    opacity: 0.85;
  }

  .cursor {
    animation: blink 1s step-end infinite;
    color: var(--accent);
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  .input-area {
    display: flex;
    gap: 0.4rem;
    padding: var(--space-3);
    border-top: 1px solid var(--border-color);
    background: var(--bg-tertiary);
    border-radius: 0 0 var(--radius-md) var(--radius-md);
  }

  .chat-input {
    flex: 1;
    padding: 0.4rem 0.6rem;
    font-size: 0.85rem;
    background: var(--bg-secondary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    outline: none;
  }

  .chat-input:focus {
    border-color: var(--accent);
  }

  .chat-input:disabled {
    opacity: 0.5;
  }

  .send-btn {
    min-width: 50px;
  }

  .error-inline {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .error-text {
    color: var(--danger-text);
    font-size: 0.85rem;
  }

  .empty-state {
    color: var(--text-secondary);
    font-style: italic;
    font-size: 0.85rem;
    margin: 0;
  }
</style>
