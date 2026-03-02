<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
  } from "../lib/stores";
  import Modal from "./Modal.svelte";

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

<Modal open={editing} title="Edit Prompt: {nodeId}" onclose={close} class="node-prompt-modal">
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
</Modal>

<style>
  :global(dialog.node-prompt-modal) {
    min-width: 500px;
    max-width: 700px;
  }

  :global(dialog.node-prompt-modal .prompt-textarea) {
    min-height: 250px;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 0.5rem;
    margin-top: var(--space-3);
  }
</style>
