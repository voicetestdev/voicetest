<script lang="ts">
  import { api } from "../lib/api";
  import { loadAgents, selectAgent } from "../lib/stores";
  import type { ImporterInfo } from "../lib/types";

  let configText = $state("");
  let agentName = $state("");
  let filePath = $state("");
  let importing = $state(false);
  let error = $state("");
  let importers = $state<ImporterInfo[]>([]);

  $effect(() => {
    api.listImporters().then((list) => {
      importers = list;
    });
  });

  async function importAgent() {
    if (!agentName.trim()) {
      error = "Please enter an agent name";
      return;
    }
    if (!configText && !filePath) {
      error = "Please provide a file path or paste JSON config";
      return;
    }
    importing = true;
    error = "";
    try {
      let agent;
      if (filePath) {
        agent = await api.createAgentFromPath(agentName, filePath);
      } else {
        const config = JSON.parse(configText);
        agent = await api.createAgent(agentName, config);
      }
      await loadAgents();
      await selectAgent(agent.id, "config");
      configText = "";
      agentName = "";
      filePath = "";
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    importing = false;
  }

  async function handleFile(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    configText = await file.text();
    filePath = "";
    if (!agentName) {
      agentName = file.name.replace(/\.json$/, "");
    }
  }
</script>

<div class="import-view">
  <h2>Import Agent</h2>

  <div class="importers">
    <span>Supported formats:</span>
    {#each importers as imp}
      <span class="tag">{imp.source_type}</span>
    {/each}
  </div>

  <div class="form-row">
    <label>
      Name:
      <input type="text" bind:value={agentName} placeholder="Agent name" />
    </label>
  </div>

  <div class="form-row">
    <label>
      Server path:
      <input type="text" bind:value={filePath} placeholder="/path/to/agent.json (optional)" />
    </label>
  </div>

  <div class="divider">or</div>

  <div class="import-options">
    <label class="file-upload">
      <input type="file" accept=".json" onchange={handleFile} />
      Upload JSON
    </label>
  </div>

  <textarea
    bind:value={configText}
    placeholder="Or paste agent config JSON here..."
    rows={14}
  ></textarea>

  <div class="button-row">
    <button onclick={importAgent} disabled={importing || (!configText && !filePath)}>
      {importing ? "Importing..." : "Import Agent"}
    </button>
  </div>

  {#if error}
    <p class="error-message">{error}</p>
  {/if}
</div>

<style>
  .import-view {
    max-width: 700px;
    overflow-y: auto;
    flex: 1;
  }

  h2 {
    margin-top: 0;
  }

  .importers {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 1.5rem;
  }

  .tag {
    background: var(--bg-hover);
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
  }

  .form-row {
    margin-bottom: 1rem;
  }

  .form-row label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
  }

  .form-row input {
    flex: 1;
  }

  .import-options {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .file-upload {
    display: inline-block;
    padding: 0.5rem 1rem;
    background: var(--bg-hover);
    border-radius: 4px;
    cursor: pointer;
  }

  .file-upload:hover {
    background: var(--border-color);
  }

  .file-upload input {
    display: none;
  }

  .divider {
    display: flex;
    align-items: center;
    gap: 1rem;
    color: var(--text-secondary);
    font-size: 0.85rem;
    margin: 1rem 0;
  }

  .divider::before,
  .divider::after {
    content: "";
    flex: 1;
    border-top: 1px solid var(--border-color);
  }

  textarea {
    width: 100%;
    resize: vertical;
    font-family: monospace;
    margin-bottom: 1rem;
  }

  .button-row {
    display: flex;
    gap: 0.5rem;
  }

  .error-message {
    color: #f87171;
    margin: 1rem 0 0 0;
  }

  @media (max-width: 480px) {
    .importers {
      flex-wrap: wrap;
    }

    .form-row label {
      flex-direction: column;
      align-items: stretch;
      gap: 0.25rem;
    }
  }
</style>
