<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { currentAgentId } from "../lib/stores";
  import {
    callState,
    startCall,
    endCall,
    toggleMute,
    resetCallState,
    liveKitStatus,
    checkLiveKitStatus,
  } from "../lib/call-store";

  let state = $derived($callState);
  let agentId = $derived($currentAgentId);
  let lkStatus = $derived($liveKitStatus);

  onMount(() => {
    checkLiveKitStatus();
  });

  onDestroy(() => {
    resetCallState();
  });

  async function handleStartCall() {
    if (!agentId || !lkStatus.available) return;
    await startCall(agentId);
  }

  async function handleEndCall() {
    if (!agentId) return;
    await endCall(agentId);
  }

  async function handleToggleMute() {
    await toggleMute();
  }
</script>

<button
  class="btn-primary"
  class:unavailable={!lkStatus.available}
  class:connecting={state.status === "connecting"}
  disabled={state.status === "connecting" || state.status === "active" || (lkStatus.available && !agentId)}
  onclick={!lkStatus.checking && !lkStatus.available ? () => checkLiveKitStatus() : handleStartCall}
  title={!lkStatus.checking && !lkStatus.available ? (lkStatus.error || "LiveKit unavailable") : undefined}
>
  {#if state.status === "connecting"}
    <span class="spinner"></span>
    Connecting...
  {:else}
    Talk to Agent
    {#if !lkStatus.available}
      <span class="btn-icon" class:spinning={lkStatus.checking}>↻</span>
    {/if}
  {/if}
</button>

{#if state.status === "active"}
  <div class="call-panel">
    <div class="call-header">
      <span class="call-status">Live Call</span>
      <div class="call-controls">
        <button
          class="btn-sm"
          class:muted={state.muted}
          onclick={handleToggleMute}
        >
          {state.muted ? "Unmute" : "Mute"}
        </button>
        <button class="btn-sm btn-danger" onclick={handleEndCall}>
          End
        </button>
      </div>
    </div>
    <div class="transcript">
      {#if state.transcript.length === 0}
        <p class="empty-state">Start speaking...</p>
      {:else}
        <div class="messages">
          {#each state.transcript as msg}
            <div class="message" class:user={msg.role === "user"} class:agent={msg.role === "assistant"}>
              <span class="role">{msg.role === "user" ? "You" : "Agent"}:</span>
              <span class="content">{msg.content}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

{#if state.status === "error"}
  <div class="error-inline">
    <span class="error-text">{state.error || "Call failed"}</span>
    <button class="btn-sm" onclick={handleStartCall}>Retry</button>
  </div>
{/if}

<style>
  .connecting {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .btn-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1em;
    height: 1em;
    vertical-align: text-top;
    margin-left: 0.4em;
    line-height: 1;
  }

  .btn-icon.spinning {
    animation: spin 1s linear infinite;
  }

  .unavailable {
    opacity: 0.5;
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

  .call-panel {
    position: fixed;
    bottom: 1rem;
    right: 1rem;
    width: 320px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 100;
  }

  .call-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-3);
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-tertiary);
    border-radius: var(--radius-md) var(--radius-md) 0 0;
  }

  .call-status {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--success-text);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .call-status::before {
    content: "";
    width: 8px;
    height: 8px;
    background: var(--success-text);
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .call-controls {
    display: flex;
    gap: 0.25rem;
  }

  .muted {
    background: var(--warning-bg);
    border-color: var(--warning-border);
    color: var(--warning-text);
  }

  .transcript {
    padding: var(--space-3);
    max-height: 200px;
    overflow-y: auto;
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

  .error-inline {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .error-text {
    color: var(--danger-text);
    font-size: 0.85rem;
  }
</style>
