<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    open: boolean;
    title: string;
    onclose: () => void;
    class?: string;
    children: Snippet;
  }

  let { open = $bindable(), title, onclose, class: className = "", children }: Props = $props();

  let dialogEl: HTMLDialogElement;

  $effect(() => {
    if (!dialogEl) return;
    if (open && !dialogEl.open) {
      dialogEl.showModal();
    } else if (!open && dialogEl.open) {
      dialogEl.close();
    }
  });

  function handleClose() {
    open = false;
    onclose();
  }

  function handleClick(e: MouseEvent) {
    // Close on backdrop click (click on dialog element itself, not its children)
    if (e.target === dialogEl) {
      handleClose();
    }
  }
</script>

<dialog
  bind:this={dialogEl}
  class="modal {className}"
  onclose={handleClose}
  onclick={handleClick}
>
  <div class="modal-header">
    <h3>{title}</h3>
    <button class="close-btn" type="button" onclick={handleClose}>&times;</button>
  </div>
  {@render children()}
</dialog>

<style>
  :global(dialog.modal) {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    max-height: 90vh;
    overflow: hidden;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
    flex-direction: column;
    padding: 0;
    color: var(--text-primary);
  }

  :global(dialog.modal[open]) {
    display: flex;
  }

  :global(dialog.modal::backdrop) {
    background: rgba(0, 0, 0, 0.5);
  }

  :global(.modal-header) {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-4);
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-tertiary);
  }

  :global(.modal-header h3) {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-primary);
  }

  :global(.modal-body) {
    padding: var(--space-4);
    overflow-y: auto;
    flex: 1;
  }

  :global(.modal-footer) {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    padding: var(--space-4);
    border-top: 1px solid var(--border-color);
    background: var(--bg-tertiary);
  }

  :global(.close-btn) {
    background: transparent;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0;
    line-height: 1;
  }

  :global(.close-btn:hover) {
    color: var(--text-primary);
    background: transparent;
  }
</style>
