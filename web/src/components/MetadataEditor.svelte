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

  let metadataExpanded = $state(false);
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

{#if $agentGraph?.source_metadata && Object.keys($agentGraph.source_metadata).length > 0}
  <section class="metadata-section">
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="metadata-header" onclick={() => { metadataExpanded = !metadataExpanded; }}>
      <h3>Metadata {metadataExpanded ? "▾" : "▸"}</h3>
    </div>
    {#if metadataExpanded}
      <div class="metadata-fields">
        {#each Object.entries($agentGraph.source_metadata).filter(([k]) => k !== "general_prompt") as [key, value]}
          <div class="metadata-field">
            <div class="metadata-label">
              <code>{key}</code>
              {#if savingMetadata === key}
                <span class="save-indicator">Saving...</span>
              {:else if metadataSaved === key}
                <span class="save-indicator saved">Saved</span>
              {/if}
            </div>
            {#if isComplexValue(value)}
              <pre class="metadata-value readonly">{JSON.stringify(value, null, 2)}</pre>
            {:else if editingMetadataKey === key}
              <textarea
                class="metadata-textarea"
                bind:value={editedMetadataValue}
                onblur={() => saveMetadataField(key)}
                disabled={savingMetadata === key}
                rows={typeof value === "string" && value.length > 100 ? 6 : 2}
              ></textarea>
            {:else}
              <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
              <span
                class="metadata-value editable"
                onclick={() => startEditingMetadata(key, value)}
                title="Click to edit"
              >{String(value) || "(empty)"}</span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </section>
{/if}
