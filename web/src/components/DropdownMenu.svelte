<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    trigger,
    children,
    minWidth = "160px",
  }: {
    trigger: Snippet<[() => void, boolean]>;
    children: Snippet;
    minWidth?: string;
  } = $props();

  let open = $state(false);
  let root = $state<HTMLElement>();
  let menu = $state<HTMLElement>();

  function toggle() {
    open = !open;
  }

  function handleWindowClick(event: MouseEvent) {
    if (!open || !root) return;
    const target = event.target as HTMLElement;
    const outside = !root.contains(target);
    const itemChosen = menu?.contains(target) && target.closest("button:not(:disabled)");
    if (outside || itemChosen) {
      open = false;
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (open && event.key === "Escape") {
      open = false;
    }
  }
</script>

<svelte:window onclick={handleWindowClick} onkeydown={handleKeydown} />

<div class="dropdown" bind:this={root}>
  {@render trigger(toggle, open)}
  {#if open}
    <ul class="dropdown-menu" role="menu" style:min-width={minWidth} bind:this={menu}>
      {@render children()}
    </ul>
  {/if}
</div>

<style>
  .dropdown {
    position: relative;
    display: inline-block;
  }

  .dropdown-menu {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    z-index: 100;
    list-style: none;
    margin: 0;
    padding: 0.25rem 0;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }

  .dropdown-menu :global(li button) {
    display: block;
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: transparent !important;
    border: none !important;
    color: var(--text-primary);
    font-size: 0.8rem;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
  }

  .dropdown-menu :global(li button:hover:not(:disabled)) {
    background: var(--bg-hover) !important;
  }

  .dropdown-menu :global(li button:disabled) {
    color: var(--text-muted);
    cursor: default;
  }

  .dropdown-menu :global(li button.danger) {
    color: var(--danger-text);
  }

  .dropdown-menu :global(.menu-separator) {
    height: 1px;
    margin: 0.25rem 0;
    background: var(--border-color);
  }
</style>
