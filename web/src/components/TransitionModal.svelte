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
  let sourceId = $state("");
  let targetId = $state("");
  let editedCondition = $state("");
  let saving = $state(false);
  let saved = $state(false);
  let transitionTextarea: HTMLTextAreaElement;

  export function open(src: string, tgt: string, condition: string) {
    sourceId = src;
    targetId = tgt;
    editedCondition = condition;
    editing = true;
    saved = false;
    requestAnimationFrame(() => {
      transitionTextarea?.focus();
    });
  }

  export function isOpen(): boolean {
    return editing;
  }

  export function close() {
    if (saving) return;
    editing = false;
    sourceId = "";
    targetId = "";
    editedCondition = "";
  }

  async function saveTransition() {
    if (!agentId || !sourceId || !targetId) return;
    saving = true;
    try {
      const result = await api.updatePrompt(
        agentId,
        sourceId,
        editedCondition,
        targetId,
      );
      agentGraph.set(result);
      saved = true;
      setTimeout(() => {
        saved = false;
        editing = false;
        sourceId = "";
        targetId = "";
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
        <h3>Edit Transition: {sourceId} → {targetId}</h3>
        <button class="close-btn" onclick={close}>&times;</button>
      </div>
      <div class="modal-body">
        <textarea
          class="prompt-textarea"
          bind:value={editedCondition}
          bind:this={transitionTextarea}
          disabled={saving}
          rows="6"
        ></textarea>
        <div class="modal-actions">
          {#if saved}
            <span class="save-indicator saved">Saved</span>
          {/if}
          <button onclick={close} disabled={saving}>Cancel</button>
          <button class="btn-primary" onclick={saveTransition} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
