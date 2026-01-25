<script lang="ts">
  import { api } from "../lib/api";
  import { loadAgents, selectAgent } from "../lib/stores";
  import type { ImporterInfo } from "../lib/types";

  let configText = $state("");
  let agentName = $state("");
  let filePath = $state("");
  let selectedFile = $state<File | null>(null);
  let importing = $state(false);
  let loadingDemo = $state(false);
  let error = $state("");
  let importers = $state<ImporterInfo[]>([]);

  const binaryExtensions = [".xlsx", ".xls"];

  $effect(() => {
    api.listImporters().then((list) => {
      importers = list;
    });
  });

  async function loadDemo() {
    loadingDemo = true;
    error = "";
    try {
      const result = await api.loadDemo();
      await loadAgents();
      await selectAgent(result.agent_id, "config");
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    loadingDemo = false;
  }

  async function importAgent() {
    if (!agentName.trim()) {
      error = "Please enter an agent name";
      return;
    }
    if (!configText && !filePath && !selectedFile) {
      error = "Please provide a file path, upload a file, or paste JSON config";
      return;
    }
    importing = true;
    error = "";
    try {
      let agent;
      if (selectedFile) {
        agent = await api.createAgentFromFile(selectedFile, agentName);
      } else if (filePath) {
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
      selectedFile = null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    importing = false;
  }

  async function handleFile(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    const isBinary = binaryExtensions.includes(ext);

    if (isBinary) {
      selectedFile = file;
      configText = `[Binary file: ${file.name}]`;
    } else {
      selectedFile = null;
      configText = await file.text();
    }

    filePath = "";
    if (!agentName) {
      agentName = file.name.replace(/\.(json|xlsx|xls)$/i, "");
    }
  }
</script>

<div class="import-view">
  <h2>Import Agent</h2>

  <div class="demo-section">
    <p>Try voicetest with a sample healthcare receptionist agent:</p>
    <button class="demo-button" onclick={loadDemo} disabled={loadingDemo}>
      {loadingDemo ? "Loading..." : "Load Demo"}
    </button>
  </div>

  <div class="divider">or import your own</div>

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
      <input type="file" accept=".json,.xlsx,.xls" onchange={handleFile} />
      Upload File
    </label>
    <span class="file-hint">.json, .xlsx (XLSForm)</span>
  </div>

  <textarea
    bind:value={configText}
    placeholder="Or paste agent config JSON here..."
    rows={14}
  ></textarea>

  <div class="button-row">
    <button onclick={importAgent} disabled={importing || (!configText && !filePath && !selectedFile)}>
      {importing ? "Importing..." : "Import Agent"}
    </button>
  </div>

  {#if error}
    <p class="error-message">{error}</p>
  {/if}
</div>

<style>
  .import-view {
    max-width: 900px;
    width: 100%;
    overflow-y: auto;
    flex: 1;
  }

  h2 {
    margin-top: 0;
  }

  .demo-section {
    background: var(--bg-hover);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .demo-section p {
    margin: 0 0 0.75rem 0;
    color: var(--text-secondary);
  }

  .demo-button {
    background: var(--accent-color, #6366f1);
    color: white;
    border: none;
    padding: 0.5rem 1.25rem;
    border-radius: 6px;
    font-weight: 500;
    cursor: pointer;
  }

  .demo-button:hover:not(:disabled) {
    opacity: 0.9;
  }

  .demo-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
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
    align-items: center;
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

  .file-hint {
    font-size: 0.8rem;
    color: var(--text-secondary);
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
    box-sizing: border-box;
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
