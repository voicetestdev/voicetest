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
