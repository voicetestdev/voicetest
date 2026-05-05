<script lang="ts">
  import { api } from "../lib/api";
  import { currentAgentId, selectRun, loadRunHistory } from "../lib/stores";
  import { get } from "svelte/store";
  import Modal from "./Modal.svelte";

  interface Props {
    show: boolean;
    onerror?: (msg: string) => void;
  }

  let { show = $bindable(false), onerror }: Props = $props();

  let file = $state<File | null>(null);
  let format = $state<"retell">("retell");
  let importing = $state(false);
  let error = $state("");

  function handleFileChange(e: Event) {
    const target = e.target as HTMLInputElement;
    file = target.files?.[0] ?? null;
    error = "";
  }

  async function handleSubmit() {
    if (!file) {
      error = "Please select a file";
      return;
    }
    const agentId = get(currentAgentId);
    if (!agentId) {
      error = "No agent selected";
      return;
    }

    importing = true;
    error = "";
    try {
      const run = await api.importCall(agentId, file, format);
      // Refresh runs list so the new run appears in the sidebar
      await loadRunHistory(agentId);
      // Navigate to the new run
      await selectRun(agentId, run.id);
      handleClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Import failed";
      error = msg;
      onerror?.(msg);
    } finally {
      importing = false;
    }
  }

  function handleClose() {
    show = false;
    file = null;
    error = "";
  }
</script>

<Modal bind:open={show} title="Import Calls" onclose={handleClose}>
  <div class="modal-body">
    <div class="field">
      <label for="import-format-select">Format</label>
      <select id="import-format-select" bind:value={format} disabled={importing}>
        <option value="retell">Retell</option>
      </select>
      <p class="hint">Retell call exports and post-call webhook payloads (JSON).</p>
    </div>

    <div class="field">
      <label for="import-file-input">Transcript file</label>
      <input
        id="import-file-input"
        type="file"
        accept=".json,application/json"
        onchange={handleFileChange}
        disabled={importing}
      />
      <p class="hint">A single call object, an array of calls, or a webhook envelope.</p>
    </div>

    {#if error}
      <p class="error-text">{error}</p>
    {/if}
  </div>

  <div class="modal-footer">
    <button class="secondary" onclick={handleClose} disabled={importing}>Cancel</button>
    <button class="btn-primary" onclick={handleSubmit} disabled={!file || importing}>
      {#if importing}
        Importing...
      {:else}
        Import
      {/if}
    </button>
  </div>
</Modal>

<style>
  .field {
    margin-bottom: var(--space-3);
  }

  .field label {
    display: block;
    margin-bottom: var(--space-2);
    font-size: var(--text-sm);
    color: var(--text-primary);
  }

  .field select,
  .field input[type="file"] {
    width: 100%;
    padding: 0.5rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
  }

  .hint {
    margin-top: 0.25rem;
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .error-text {
    color: var(--danger-text);
    font-size: 0.85rem;
    margin-top: var(--space-2);
  }

  .secondary {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
  }

  .secondary:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }
</style>
