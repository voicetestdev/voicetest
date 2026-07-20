<script lang="ts">
  import { toasts, dismissToast } from "../lib/toast";
</script>

<div class="toasts" role="status" aria-live="polite">
  {#each $toasts as toast (toast.id)}
    <div class="toast">
      <span class="toast-message">{toast.message}</span>
      <button class="toast-close" onclick={() => dismissToast(toast.id)} aria-label="Dismiss">
        ×
      </button>
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    bottom: 1rem;
    right: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 1000;
    max-width: min(90vw, 28rem);
  }

  .toast {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    background: var(--toast-bg, #333);
    color: var(--toast-fg, #fff);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
  }

  .toast-message {
    flex: 1;
    word-break: break-word;
  }

  .toast-close {
    background: none;
    border: none;
    color: inherit;
    font-size: 1.1rem;
    line-height: 1;
    cursor: pointer;
    padding: 0;
  }
</style>
