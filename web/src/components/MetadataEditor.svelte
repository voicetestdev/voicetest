<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
  } from "../lib/stores";

  interface Props {
    agentId: string;
    onerror?: (msg: string) => void;
  }

  let { agentId, onerror }: Props = $props();

  let editingMetadataKey = $state<string | null>(null);
  let editedMetadataValue = $state("");
  let savingMetadata = $state<string | null>(null);
  let metadataSaved = $state<string | null>(null);

  function reportError(msg: string) {
    onerror?.(msg);
  }

  function startEditingMetadata(key: string, value: unknown) {
    editingMetadataKey = key;
    editedMetadataValue = typeof value === "string" ? value : JSON.stringify(value);
  }

  async function saveMetadataField(key: string) {
    if (!agentId) {
      editingMetadataKey = null;
      return;
    }
    const current = $agentGraph?.source_metadata?.[key];
    const currentStr = typeof current === "string" ? current : JSON.stringify(current);
    if (editedMetadataValue === currentStr) {
      editingMetadataKey = null;
      return;
    }
    savingMetadata = key;
    try {
      let parsed: unknown = editedMetadataValue;
      if (typeof current === "number") {
        parsed = Number(editedMetadataValue);
      } else if (typeof current === "boolean") {
        parsed = editedMetadataValue === "true";
      }
      const result = await api.updateMetadata(agentId, { [key]: parsed });
      agentGraph.set(result);
      editingMetadataKey = null;
      metadataSaved = key;
      setTimeout(() => { metadataSaved = null; }, 2000);
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    savingMetadata = null;
  }

  function isComplexValue(value: unknown): boolean {
    return typeof value === "object" && value !== null;
  }
</script>

{#if $agentGraph?.source_metadata && Object.keys($agentGraph.source_metadata).filter(k => k !== "general_prompt").length > 0}
  <section class="metadata-panel">
    <h3>Metadata</h3>
    <div class="metadata-grid">
      {#each Object.entries($agentGraph.source_metadata).filter(([k]) => k !== "general_prompt") as [key, value]}
        <div class="metadata-row">
          <span class="metadata-key">{key}</span>
          <span class="metadata-val">
            {#if isComplexValue(value)}
              <pre class="metadata-complex">{JSON.stringify(value, null, 2)}</pre>
            {:else if editingMetadataKey === key}
              <textarea
                class="metadata-input"
                bind:value={editedMetadataValue}
                onblur={() => saveMetadataField(key)}
                disabled={savingMetadata === key}
                rows={typeof value === "string" && value.length > 100 ? 6 : 2}
              ></textarea>
            {:else}
              <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
              <span
                class="metadata-editable"
                onclick={() => startEditingMetadata(key, value)}
                title="Click to edit"
              >{String(value) || "(empty)"}</span>
            {/if}
            {#if savingMetadata === key}
              <span class="save-indicator">Saving...</span>
            {:else if metadataSaved === key}
              <span class="save-indicator saved">Saved</span>
            {/if}
          </span>
        </div>
      {/each}
    </div>
  </section>
{/if}

<style>
  .metadata-panel {
    margin-bottom: 1.5rem;
    padding: var(--space-4);
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
  }

  .metadata-panel h3 {
    margin: 0 0 var(--space-3) 0;
    font-size: 1rem;
    color: var(--text-secondary);
  }

  .metadata-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--space-2) var(--space-4);
  }

  .metadata-row {
    display: contents;
  }

  .metadata-key {
    color: var(--text-secondary);
    font-size: var(--text-sm);
    font-family: monospace;
    padding-top: 0.15rem;
  }

  .metadata-val {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    min-width: 0;
  }

  .metadata-editable {
    cursor: pointer;
    padding: 0.15rem 0.4rem;
    margin: -0.15rem -0.4rem;
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    color: var(--text-primary);
    transition: background 0.15s;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .metadata-editable:hover {
    background: var(--bg-hover);
  }

  .metadata-complex {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: var(--text-sm);
    color: var(--text-secondary);
    line-height: 1.5;
    max-height: 200px;
    overflow-y: auto;
    background: var(--bg-tertiary);
    padding: 0.5rem;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
  }

  .metadata-input {
    width: 100%;
    padding: 0.5rem;
    font-family: monospace;
    font-size: var(--text-sm);
    line-height: 1.5;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--accent-color, #6366f1);
    border-radius: var(--radius-sm);
    resize: vertical;
    box-sizing: border-box;
  }

  .save-indicator {
    font-size: var(--text-xs);
    color: var(--text-muted);
    white-space: nowrap;
  }

  .save-indicator.saved {
    color: var(--color-pass, #3fb950);
  }
</style>
