<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
  } from "../lib/stores";
  import type { GlobalNodeSetting } from "../lib/types";
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
  let globalSetting = $state<GlobalNodeSetting | null>(null);
  let saving = $state(false);
  let saved = $state(false);
  let nodePromptTextarea: HTMLTextAreaElement;

  export function open(id: string, prompt: string) {
    nodeId = id;
    editedNodePrompt = prompt;
    globalSetting = $agentGraph?.nodes[id]?.global_node_setting ?? null;
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

<Modal open={editing} title="{globalSetting ? 'Edit Global Node' : 'Edit Prompt'}: {nodeId}" onclose={close} class="node-prompt-modal">
  <div class="modal-body">
    <textarea
      class="prompt-textarea"
      bind:value={editedNodePrompt}
      bind:this={nodePromptTextarea}
      disabled={saving}
      rows="15"
    ></textarea>
    {#if globalSetting}
      <div class="global-node-info">
        <div class="global-field">
          <label class="global-label">Entry condition</label>
          <div class="global-value">{globalSetting.condition}</div>
        </div>
        {#if globalSetting.go_back_conditions.length > 0}
          <div class="global-field">
            <label class="global-label">Go-back conditions</label>
            {#each globalSetting.go_back_conditions as gb}
              <div class="global-value">{gb.condition.value}</div>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
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
    width: 100%;
    min-height: 250px;
    padding: 0.5rem;
    font-family: monospace;
    font-size: var(--text-sm);
    line-height: 1.5;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--accent-color, #6366f1);
    border-radius: var(--radius-sm);
    resize: vertical;
    outline: none;
    box-sizing: border-box;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 0.5rem;
    margin-top: var(--space-3);
  }

  .global-node-info {
    margin-top: var(--space-3);
    padding: var(--space-3);
    border: 1px solid #7c3aed;
    border-radius: var(--radius-sm);
    background: rgba(124, 58, 237, 0.05);
  }

  .global-field {
    margin-bottom: var(--space-2);
  }

  .global-field:last-child {
    margin-bottom: 0;
  }

  .global-label {
    display: block;
    font-size: var(--text-sm);
    font-weight: 600;
    color: #7c3aed;
    margin-bottom: 0.25rem;
  }

  .global-value {
    font-size: var(--text-sm);
    color: var(--text-secondary);
    white-space: pre-wrap;
    padding: 0.25rem 0.5rem;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    margin-bottom: 0.25rem;
  }

  .global-value:last-child {
    margin-bottom: 0;
  }
</style>
