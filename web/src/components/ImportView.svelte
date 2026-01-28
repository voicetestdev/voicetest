<script lang="ts">
  import { api } from "../lib/api";
  import { loadAgents, selectAgent } from "../lib/stores";
  import type { ImporterInfo, Platform, PlatformInfo, PlatformStatus, RemoteAgentInfo } from "../lib/types";

  let configText = $state("");
  let agentName = $state("");
  let filePath = $state("");
  let selectedFile = $state<File | null>(null);
  let importing = $state(false);
  let loadingDemo = $state(false);
  let error = $state("");
  let importers = $state<ImporterInfo[]>([]);

  let activeTab = $state<string>("file");
  let showServerPath = $state(false);
  let platforms = $state<PlatformInfo[]>([]);
  let platformStatus = $state<Record<string, PlatformStatus>>({});
  let platformAgents = $state<Record<string, RemoteAgentInfo[]>>({});
  let loadingAgents = $state(false);
  let selectedRemoteAgent = $state<RemoteAgentInfo | null>(null);
  let apiKeyInput = $state("");
  let configuringPlatform = $state(false);

  const binaryExtensions = [".xlsx", ".xls"];

  const platformDisplayNames: Record<string, string> = {
    retell: "Retell",
    vapi: "VAPI",
    livekit: "LiveKit",
    bland: "Bland",
  };

  function getPlatformDisplayName(platform: string): string {
    return platformDisplayNames[platform] || platform.charAt(0).toUpperCase() + platform.slice(1);
  }

  $effect(() => {
    api.listImporters().then((list) => {
      importers = list;
    });
    api.listPlatforms().then((list) => {
      platforms = list;
      for (const p of list) {
        platformStatus[p.name] = { platform: p.name, configured: p.configured };
      }
    }).catch(() => {});
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

  function handlePathBlur() {
    if (!agentName && filePath) {
      const filename = filePath.split("/").pop() || "";
      agentName = filename.replace(/\.(json|xlsx|xls)$/i, "");
    }
  }

  function switchTab(tab: string) {
    activeTab = tab;
    error = "";
    selectedRemoteAgent = null;
    apiKeyInput = "";

    if (tab !== "file" && platformStatus[tab]?.configured) {
      loadRemoteAgents(tab);
    }
  }

  async function loadRemoteAgents(platform: Platform) {
    loadingAgents = true;
    error = "";
    try {
      const agents = await api.listRemoteAgents(platform);
      platformAgents[platform] = agents;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    loadingAgents = false;
  }

  async function configurePlatform(platform: Platform) {
    if (!apiKeyInput.trim()) {
      error = "Please enter an API key";
      return;
    }
    configuringPlatform = true;
    error = "";
    try {
      const status = await api.configurePlatform(platform, apiKeyInput);
      platformStatus[platform] = status;
      apiKeyInput = "";
      await loadRemoteAgents(platform);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    configuringPlatform = false;
  }

  async function importRemoteAgent(platform: Platform) {
    if (!selectedRemoteAgent) {
      error = "Please select an agent to import";
      return;
    }
    importing = true;
    error = "";
    try {
      const graph = await api.importRemoteAgent(platform, selectedRemoteAgent.id);
      const name = agentName.trim() || selectedRemoteAgent.name;
      const agent = await api.createAgent(name, graph);
      await loadAgents();
      await selectAgent(agent.id, "config");
      selectedRemoteAgent = null;
      agentName = "";
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    importing = false;
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

  <div class="tabs">
    <button
      class="tab"
      class:active={activeTab === "file"}
      onclick={() => switchTab("file")}
    >
      From File
    </button>
    {#each platforms as platform}
      <button
        class="tab"
        class:active={activeTab === platform.name}
        onclick={() => switchTab(platform.name)}
      >
        From {getPlatformDisplayName(platform.name)}
      </button>
    {/each}
  </div>

  {#if activeTab === "file"}
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
      rows={12}
    ></textarea>

    <div class="button-row">
      <button onclick={importAgent} disabled={importing || (!configText && !filePath && !selectedFile)}>
        {importing ? "Importing..." : "Import Agent"}
      </button>
    </div>

    <div class="server-path-section">
      <button class="link-toggle" onclick={() => showServerPath = !showServerPath}>
        {showServerPath ? "▼" : "▶"} Link to server file
      </button>
      {#if showServerPath}
        <div class="server-path-input">
          <input
            type="text"
            bind:value={filePath}
            placeholder="/path/to/agent.json"
            onblur={handlePathBlur}
          />
          <button
            onclick={importAgent}
            disabled={importing || !filePath}
          >
            {importing ? "Linking..." : "Link"}
          </button>
        </div>
        <p class="hint">Link to a file on the server. Changes to the file will be reflected when reloading.</p>
      {/if}
    </div>
  {:else}
    {@const platform = activeTab}
    {@const status = platformStatus[platform]}
    {@const agents = platformAgents[platform] || []}
    {@const displayName = getPlatformDisplayName(platform)}

    <div class="platform-section">
      {#if !status?.configured}
        <div class="api-key-setup">
          <p>Connect your {displayName} account to import agents directly.</p>
          <div class="api-key-form">
            <input
              type="password"
              bind:value={apiKeyInput}
              placeholder="{displayName} API Key"
              class="api-key-input"
            />
            <button
              onclick={() => configurePlatform(platform)}
              disabled={configuringPlatform || !apiKeyInput.trim()}
            >
              {configuringPlatform ? "Connecting..." : "Connect"}
            </button>
          </div>
          <p class="hint">Your API key is stored locally in settings.</p>
        </div>
      {:else}
        <div class="connected-status">
          <span class="connected-badge">Connected</span>
          <span class="hint">To change the API key, go to Settings.</span>
        </div>

        <div class="form-row">
          <label>
            Name (optional):
            <input type="text" bind:value={agentName} placeholder="Override agent name" />
          </label>
        </div>

        {#if loadingAgents}
          <p class="loading">Loading agents...</p>
        {:else if agents.length === 0}
          <p class="empty-state">No agents found in your {displayName} account.</p>
        {:else}
          <div class="agents-list">
            <p class="list-label">Select an agent to import:</p>
            {#each agents as agent}
              <button
                class="agent-item"
                class:selected={selectedRemoteAgent?.id === agent.id}
                onclick={() => (selectedRemoteAgent = agent)}
              >
                <span class="agent-name">{agent.name}</span>
                <span class="agent-id">{agent.id}</span>
              </button>
            {/each}
          </div>

          <div class="button-row">
            <button
              onclick={() => importRemoteAgent(platform)}
              disabled={importing || !selectedRemoteAgent}
            >
              {importing ? "Importing..." : "Import Selected"}
            </button>
          </div>
        {/if}
      {/if}
    </div>
  {/if}

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

  .tabs {
    display: flex;
    gap: 0.25rem;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 0.5rem;
    flex-wrap: wrap;
  }

  .tab {
    background: transparent;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px 6px 0 0;
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 0.9rem;
  }

  .tab:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .tab.active {
    background: var(--bg-hover);
    color: var(--text-primary);
    font-weight: 500;
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

  .server-path-section {
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .link-toggle {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.25rem 0;
    font-size: 0.85rem;
  }

  .link-toggle:hover {
    color: var(--text-primary);
  }

  .server-path-input {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
  }

  .server-path-input input {
    flex: 1;
    font-family: monospace;
  }

  .error-message {
    color: #f87171;
    margin: 1rem 0 0 0;
  }

  .platform-section {
    padding: 0.5rem 0;
  }

  .api-key-setup {
    background: var(--bg-hover);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.5rem;
  }

  .api-key-setup p {
    margin: 0 0 1rem 0;
    color: var(--text-secondary);
  }

  .api-key-form {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .api-key-input {
    flex: 1;
    font-family: monospace;
  }

  .hint {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin: 0;
  }

  .connected-status {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .connected-badge {
    background: #166534;
    color: white;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 500;
  }

  .loading {
    color: var(--text-secondary);
    font-style: italic;
  }

  .empty-state {
    color: var(--text-secondary);
    font-style: italic;
    padding: 2rem 0;
  }

  .agents-list {
    margin-bottom: 1rem;
  }

  .list-label {
    color: var(--text-secondary);
    font-size: 0.85rem;
    margin: 0 0 0.75rem 0;
  }

  .agent-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 0.75rem 1rem;
    background: var(--bg-hover);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    margin-bottom: 0.5rem;
    cursor: pointer;
    text-align: left;
  }

  .agent-item:hover {
    background: var(--border-color);
  }

  .agent-item.selected {
    border-color: var(--accent-color, #6366f1);
    background: var(--bg-tertiary);
  }

  .agent-name {
    font-weight: 500;
    color: var(--text-primary);
  }

  .agent-id {
    font-family: monospace;
    font-size: 0.8rem;
    color: var(--text-muted);
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

    .tabs {
      flex-wrap: wrap;
    }

    .api-key-form {
      flex-direction: column;
    }
  }
</style>
