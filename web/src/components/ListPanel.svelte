<script lang="ts">
  import type { Snippet } from "svelte";

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();
</script>

<section class="list-panel">
  {@render children()}
</section>

<style>
  .list-panel {
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    padding: var(--space-4);
  }

  /* Table layout — padding on cells, collapse makes borders edge-to-edge */
  .list-panel :global(table) {
    width: 100%;
    border-collapse: collapse;
  }

  .list-panel :global(th),
  .list-panel :global(td) {
    padding: var(--space-2) var(--space-3);
    text-align: left;
    border-bottom: 1px solid var(--border-color);
  }

  .list-panel :global(th) {
    color: var(--text-secondary);
    font-weight: 500;
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .list-panel :global(tbody tr) {
    transition: background 80ms ease-out;
  }

  .list-panel :global(tbody tr:hover) {
    background: var(--bg-hover);
  }

  .list-panel :global(tbody tr.selected) {
    background: var(--bg-tertiary);
  }

  /* List layout — negative margin pulls the list to the container edges
     so button borders run edge-to-edge, matching table border-collapse */
  .list-panel :global(ul) {
    list-style: none;
    padding: 0;
    margin: calc(-1 * var(--space-4));
    margin-top: 0;
  }

  .list-panel :global(ul:first-child) {
    margin-top: calc(-1 * var(--space-4));
  }

  .list-panel :global(ul > li > button) {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-3) var(--space-4);
    background: none;
    border: none;
    border-bottom: 1px solid var(--border-color);
    cursor: pointer;
    color: var(--text-primary);
    font-size: var(--text-sm);
    text-align: left;
    transition: background 80ms ease-out;
  }

  .list-panel :global(ul > li:last-child > button) {
    border-bottom: none;
  }

  .list-panel :global(ul > li > button:hover) {
    background: var(--bg-hover);
  }

  .list-panel :global(ul > li > button.selected) {
    background: var(--bg-tertiary);
  }
</style>
