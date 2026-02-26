<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
  } from "../lib/stores";

  interface Props {
    agentId: string;
    onerror?: (msg: string) => void;
    ontooltipschanged?: () => void;
  }

  let { agentId, onerror, ontooltipschanged }: Props = $props();

  let editing = $state(false);
  let nodeId = $state("");
  let editedNodePrompt = $state("");
  let saving = $state(false);
  let saved = $state(false);
  let nodePromptTextarea: HTMLTextAreaElement;

  export function open(id: string, prompt: string) {
    nodeId = id;
    editedNodePrompt = prompt;
    editing = true;
    saved = false;
    requestAnimationFrame(() => {
      nodePromptTextarea?.focus();
    });
  }

  export function isOpen(): boolean {
    return editing;
  }

  export function close() {
    if (saving) return;
    editing = false;
    nodeId = "";
    editedNodePrompt = "";
  }

  async function saveNodePrompt() {
    if (!agentId || !nodeId) return;
    saving = true;
    try {
      const result = await api.updatePrompt(agentId, nodeId, editedNodePrompt);
      agentGraph.set(result);
      saved = true;
      setTimeout(() => {
        saved = false;
        editing = false;
        nodeId = "";
      }, 800);
      ontooltipschanged?.();
    } catch (e) {
      onerror?.(e instanceof Error ? e.message : String(e));
    }
    saving = false;
  }
</script>

{#if editing}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="modal-backdrop" onclick={(e) => { if ((e.target as HTMLElement).classList.contains("modal-backdrop")) close(); }}>
    <div class="modal node-prompt-modal">
      <div class="modal-header">
        <h3>Edit Prompt: {nodeId}</h3>
        <button class="close-btn" onclick={close}>&times;</button>
      </div>
      <div class="modal-body">
        <textarea
          class="prompt-textarea"
          bind:value={editedNodePrompt}
          bind:this={nodePromptTextarea}
          disabled={saving}
          rows="15"
        ></textarea>
        <div class="modal-actions">
          {#if saved}
            <span class="save-indicator saved">Saved</span>
          {/if}
          <button onclick={close} disabled={saving}>Cancel</button>
          <button class="btn-primary" onclick={saveNodePrompt} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
