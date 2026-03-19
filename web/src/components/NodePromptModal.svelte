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
  let editedCondition = $state("");
  let editedGoBacks = $state<{ id: string; condition: string }[]>([]);
  let isGlobal = $state(false);
  let saving = $state(false);
  let saved = $state(false);
  let nodePromptTextarea: HTMLTextAreaElement;

  export function open(id: string, prompt: string) {
    nodeId = id;
    editedNodePrompt = prompt;
    const gns = $agentGraph?.nodes[id]?.global_node_setting ?? null;
    if (gns) {
      isGlobal = true;
      editedCondition = gns.condition;
      editedGoBacks = gns.go_back_conditions.map(gb => ({
        id: gb.id,
        condition: gb.condition.value,
      }));
    } else {
      isGlobal = false;
      editedCondition = "";
      editedGoBacks = [];
    }
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

  function addGoBack() {
    editedGoBacks = [
      ...editedGoBacks,
      { id: `go-back-${Date.now()}`, condition: "" },
    ];
  }

  function removeGoBack(index: number) {
    editedGoBacks = editedGoBacks.filter((_, i) => i !== index);
  }

  async function save() {
    if (!agentId || !nodeId) return;
    saving = true;
    try {
      // Save the prompt
      let result = await api.updatePrompt(agentId, nodeId, editedNodePrompt);

      // Save global node setting if applicable
      if (isGlobal && editedCondition.trim()) {
        result = await api.updateGlobalNodeSetting(agentId, nodeId, {
          condition: editedCondition,
          go_back_conditions: editedGoBacks.filter(gb => gb.condition.trim()),
        });
      } else if (!isGlobal) {
        // Remove global setting if it was toggled off
        const hadGlobal = $agentGraph?.nodes[nodeId]?.global_node_setting != null;
        if (hadGlobal) {
          result = await api.deleteGlobalNodeSetting(agentId, nodeId);
        }
      }

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

<Modal open={editing} title="{isGlobal ? 'Edit Global Node' : 'Edit Prompt'}: {nodeId}" onclose={close} class="node-prompt-modal">
  <div class="modal-body">
    <label class="field-label">State prompt</label>
    <textarea
      class="prompt-textarea"
      bind:value={editedNodePrompt}
      bind:this={nodePromptTextarea}
      disabled={saving}
      rows="15"
    ></textarea>
    <div class="global-toggle">
      <label>
        <input type="checkbox" bind:checked={isGlobal} disabled={saving} />
        Global node (reachable from any conversation node)
      </label>
    </div>
    {#if isGlobal}
      <div class="global-node-info">
        <div class="global-field">
          <label class="global-label">Entry condition</label>
          <textarea
            class="global-textarea"
            bind:value={editedCondition}
            disabled={saving}
            rows="3"
            placeholder="Condition that triggers entry from any conversation node"
          ></textarea>
        </div>
        <div class="global-field">
          <label class="global-label">Go-back conditions</label>
          {#each editedGoBacks as gb, i}
            <div class="go-back-row">
              <textarea
                class="global-textarea go-back-input"
                bind:value={gb.condition}
                disabled={saving}
                rows="2"
                placeholder="Condition to return to the originating node"
              ></textarea>
              <button
                class="remove-go-back"
                onclick={() => removeGoBack(i)}
                disabled={saving}
                title="Remove"
              >&times;</button>
            </div>
          {/each}
          <button class="add-go-back" onclick={addGoBack} disabled={saving}>
            + Add go-back condition
          </button>
        </div>
      </div>
    {/if}
    <div class="modal-actions">
      {#if saved}
        <span class="save-indicator saved">Saved</span>
      {/if}
      <button onclick={close} disabled={saving}>Cancel</button>
      <button class="btn-primary" onclick={save} disabled={saving}>
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

  .field-label {
    display: block;
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 0.25rem;
  }

  .global-toggle {
    margin-top: var(--space-2);
    font-size: var(--text-sm);
    color: var(--text-secondary);
  }

  .global-toggle input[type="checkbox"] {
    margin-right: 0.35rem;
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

  .global-textarea {
    width: 100%;
    padding: 0.5rem;
    font-family: monospace;
    font-size: var(--text-sm);
    line-height: 1.5;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid #7c3aed;
    border-radius: var(--radius-sm);
    resize: vertical;
    outline: none;
    box-sizing: border-box;
  }

  .go-back-row {
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    margin-bottom: 0.5rem;
  }

  .go-back-input {
    flex: 1;
  }

  .remove-go-back {
    background: none;
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    font-size: 1.1rem;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    line-height: 1;
    flex-shrink: 0;
  }

  .remove-go-back:hover {
    color: #f87171;
    border-color: #f87171;
  }

  .add-go-back {
    background: none;
    border: 1px dashed var(--border-color);
    color: #7c3aed;
    font-size: var(--text-sm);
    padding: 0.35rem 0.75rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    width: 100%;
  }

  .add-go-back:hover {
    border-color: #7c3aed;
    background: rgba(124, 58, 237, 0.05);
  }
</style>
