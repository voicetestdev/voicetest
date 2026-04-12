<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import { agents, loadAgents, selectAgent } from "../lib/stores";
  import type { Platform, PlatformInfo, PlatformStatus, RemoteAgentInfo } from "../lib/types";

  let configText = $state("");
  let agentName = $state("");
  let filePath = $state("");
  let selectedFile = $state<File | null>(null);
  let importing = $state(false);
  let loadingDemo = $state(false);
  let error = $state("");

  let activeMethod = $state<string>("dropzone");
  let platforms = $state<PlatformInfo[]>([]);
  let platformStatus = $state<Record<string, PlatformStatus>>({});
  let platformAgents = $state<Record<string, RemoteAgentInfo[]>>({});
  let loadingAgents = $state(false);
  let selectedRemoteAgent = $state<RemoteAgentInfo | null>(null);
  let apiKeyInput = $state("");
  let apiSecretInput = $state("");
  let configuringPlatform = $state(false);
  let fetchedGraph = $state<object | null>(null);

  let showJson = $state(false);
  let demoDismissed = $state(false);
  let dragging = $state(false);

  let fileInputRef = $state<HTMLInputElement | null>(null);

  let hasInput = $derived(!!configText || !!selectedFile || !!filePath || !!fetchedGraph);
  let showDemo = $derived($agents.length === 0 && !demoDismissed);
  let jsonToggleLabel = $derived(hasInput ? "View JSON" : "Paste or view JSON");

  const binaryExtensions = [".xlsx", ".xls"];

  const platformDisplayNames: Record<string, string> = {
    retell: "Retell",
    vapi: "VAPI",
    livekit: "LiveKit",
    bland: "Bland",
    telnyx: "Telnyx",
  };

  function getPlatformDisplayName(platform: string): string {
    return platformDisplayNames[platform] || platform.charAt(0).toUpperCase() + platform.slice(1);
  }

  function platformNeedsSecret(platform: string): boolean {
    return platform === "livekit";
  }

  // All non-active methods listed as toggles
  type MethodDef = { id: string; label: string };
  let allMethods = $derived<MethodDef[]>([
    { id: "dropzone", label: "Upload a file" },
    { id: "serverpath", label: "Link to server file" },
    ...platforms.map((p) => ({ id: p.name, label: `Import from ${getPlatformDisplayName(p.name)}` })),
  ]);
  onMount(() => {
    api.listPlatforms().then((list) => {
      platforms = list;
      platformStatus = Object.fromEntries(
        list.map((p) => [p.name, { platform: p.name, configured: p.configured }])
      );
    }).catch(() => {});
  });

  function clearData() {
    configText = "";
    agentName = "";
    filePath = "";
    selectedFile = null;
    fetchedGraph = null;
    selectedRemoteAgent = null;
    apiKeyInput = "";
    apiSecretInput = "";
    error = "";
    showJson = false;
    if (fileInputRef) fileInputRef.value = "";
  }

  function switchMethod(method: string) {
    clearData();
    activeMethod = method;
    if (method !== "dropzone" && method !== "serverpath" && platformStatus[method]?.configured) {
      loadRemoteAgents(method);
    }
  }

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
      error = "Please provide a file, path, or JSON config";
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
      clearData();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    importing = false;
  }

  function processFile(file: File) {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    const isBinary = binaryExtensions.includes(ext);

    if (isBinary) {
      selectedFile = file;
      configText = `[Binary file: ${file.name}]`;
    } else {
      selectedFile = null;
      file.text().then((text) => {
        configText = text;
      });
    }

    filePath = "";
    fetchedGraph = null;
    if (!agentName) {
      agentName = file.name.replace(/\.(json|xlsx|xls)$/i, "");
    }
  }

  function handleFile(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    processFile(file);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const file = e.dataTransfer?.files?.[0];
    if (!file) return;
    processFile(file);
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    dragging = true;
  }

  function handleDragLeave() {
    dragging = false;
  }

  function handlePathBlur() {
    if (!agentName && filePath) {
      const filename = filePath.split("/").pop() || "";
      agentName = filename.replace(/\.(json|xlsx|xls)$/i, "");
    }
  }

  function changeFile() {
    configText = "";
    selectedFile = null;
    agentName = "";
    fetchedGraph = null;
    if (fileInputRef) fileInputRef.value = "";
  }

  async function loadRemoteAgents(platform: Platform) {
    loadingAgents = true;
    error = "";
    try {
      const remoteAgents = await api.listRemoteAgents(platform);
      platformAgents = { ...platformAgents, [platform]: remoteAgents };
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      // If credentials are missing/invalid, show the setup form instead of error
      if (message.includes("API_KEY") || message.includes("API_SECRET") || message.includes("credentials") || message.includes("Unauthorized") || message.includes("401")) {
        platformStatus = { ...platformStatus, [platform]: { platform, configured: false } };
      } else {
        error = message;
      }
    }
    loadingAgents = false;
  }

  async function configurePlatform(platform: Platform) {
    if (!apiKeyInput.trim()) {
      error = "Please enter an API key";
      return;
    }
    if (platformNeedsSecret(platform) && !apiSecretInput.trim()) {
      error = "Please enter an API secret";
      return;
    }
    configuringPlatform = true;
    error = "";
    try {
      const secret = platformNeedsSecret(platform) ? apiSecretInput : undefined;
      const status = await api.configurePlatform(platform, apiKeyInput, secret);
      platformStatus = { ...platformStatus, [platform]: status };
      apiKeyInput = "";
      apiSecretInput = "";
      await loadRemoteAgents(platform);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    configuringPlatform = false;
  }

  async function selectRemoteAgent(platform: Platform, agent: RemoteAgentInfo) {
    selectedRemoteAgent = agent;
    error = "";
    try {
      const graph = await api.importRemoteAgent(platform, agent.id);
      fetchedGraph = graph;
      configText = JSON.stringify(graph, null, 2);
      if (!agentName) {
        agentName = agent.name;
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      fetchedGraph = null;
    }
  }
</script>

<div class="import-view">
  <h2>Import Agent</h2>

  {#if showDemo}
    <div class="demo-banner">
      <span>New here? Try a sample agent.</span>
      <button class="demo-button" onclick={loadDemo} disabled={loadingDemo}>
        {loadingDemo ? "Loading..." : "Load Demo"}
      </button>
      <button class="dismiss-button" onclick={() => demoDismissed = true} aria-label="Dismiss">&times;</button>
    </div>
  {/if}

  <!-- Source Section -->
  <div class="section">
    <div class="section-header">Source</div>
    <div class="section-body">

      {#each allMethods as method}
        {@const isActive = method.id === activeMethod}
        <div class="method-entry" class:active={isActive}>
          <button
            class="method-toggle"
            onclick={() => switchMethod(isActive ? "" : method.id)}
          >
            <span class="caret" class:open={isActive}>▶</span> {method.label}
          </button>

          {#if isActive}
            <div class="method-content">
              {#if method.id === "dropzone"}
                {#if selectedFile || (configText && !configText.startsWith("[Binary file:"))}
                  <div class="file-status">
                    <span class="file-status-check">&#10003;</span>
                    <span class="file-status-name">{selectedFile?.name || "file loaded"}</span>
                    <button class="change-button" onclick={changeFile}>Change</button>
                  </div>
                {:else}
                  <!-- svelte-ignore a11y_no_static_element_interactions -->
                  <div
                    class="drop-zone"
                    class:dragging
                    ondrop={handleDrop}
                    ondragover={handleDragOver}
                    ondragleave={handleDragLeave}
                  >
                    <p>Drop a file here or click to upload</p>
                    <label class="choose-file-button">
                      <input
                        type="file"
                        accept=".json,.xlsx,.xls"
                        onchange={handleFile}
                        bind:this={fileInputRef}
                      />
                      Choose File
                    </label>
                    <span class="file-types">.json, .xlsx</span>
                  </div>
                {/if}

              {:else if method.id === "serverpath"}
                <input
                  type="text"
                  bind:value={filePath}
                  placeholder="/path/to/agent.json"
                  onblur={handlePathBlur}
                />
                <p class="hint">File stays linked — changes sync on reload.</p>

              {:else}
                {@const platform = method.id}
                {@const status = platformStatus[platform]}
                {@const remoteAgents = platformAgents[platform] || []}
                {@const displayName = getPlatformDisplayName(platform)}

                {#if !status?.configured}
                  <p class="platform-prompt">Connect your {displayName} account.</p>
                  <div class="api-key-form">
                    <input
                      type="password"
                      bind:value={apiKeyInput}
                      placeholder="API Key"
                      class="api-key-input"
                    />
                    {#if platformNeedsSecret(platform)}
                      <input
                        type="password"
                        bind:value={apiSecretInput}
                        placeholder="API Secret"
                        class="api-key-input"
                      />
                    {/if}
                    <button
                      onclick={() => configurePlatform(platform)}
                      disabled={configuringPlatform || !apiKeyInput.trim() || (platformNeedsSecret(platform) && !apiSecretInput.trim())}
                    >
                      {configuringPlatform ? "Connecting..." : "Connect"}
                    </button>
                  </div>
                  <p class="hint">Credentials stored locally.</p>
                {:else}
                  <div class="connected-status">
                    <span class="connected-badge">&#10003; Connected to {displayName}</span>
                  </div>

                  {#if loadingAgents}
                    <p class="loading">Loading agents...</p>
                  {:else if remoteAgents.length === 0}
                    <p class="empty-state">No agents found in your {displayName} account.</p>
                  {:else}
                    <div class="agents-list">
                      {#each remoteAgents as agent}
                        <button
                          class="agent-item"
                          class:selected={selectedRemoteAgent?.id === agent.id}
                          onclick={() => selectRemoteAgent(platform, agent)}
                        >
                          <span class="agent-radio">{selectedRemoteAgent?.id === agent.id ? "◉" : "○"}</span>
                          <span class="agent-name">{agent.name}</span>
                          <span class="agent-id">{agent.id}</span>
                        </button>
                      {/each}
                    </div>
                  {/if}
                {/if}
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  </div>

  <!-- Details Section -->
  <div class="section">
    <div class="section-header">Details</div>
    <div class="section-body">
      {#if importing}
        <div class="importing-state">
          <span class="spinner"></span>
          <span>Importing agent...</span>
        </div>
      {:else}
        <div class="form-row">
          <label>
            Name:
            <input type="text" bind:value={agentName} placeholder="Agent name" />
          </label>
        </div>

        <button class="method-toggle" onclick={() => showJson = !showJson}>
          <span class="caret" class:open={showJson}>▶</span> {jsonToggleLabel}
        </button>

        {#if showJson}
          <textarea
            bind:value={configText}
            placeholder="Paste agent config JSON here..."
            rows={12}
            class="json-editor"
          ></textarea>
        {/if}

        <div class="button-row">
          <button
            class="import-button"
            onclick={importAgent}
            disabled={!hasInput}
          >
            Import Agent
          </button>
        </div>
      {/if}
    </div>
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

  /* Demo banner */
  .demo-banner {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    background: var(--bg-secondary);
    border: 1px dashed var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-3) var(--space-4);
    margin-bottom: 1rem;
    font-size: var(--text-sm);
    color: var(--text-secondary);
  }

  .demo-banner .demo-button {
    background: var(--accent);
    color: #ffffff;
    border: 1px solid var(--accent);
    padding: 0.35rem 1rem;
    border-radius: var(--radius-md);
    font-weight: 500;
    cursor: pointer;
    font-size: var(--text-sm);
  }

  .demo-banner .demo-button:hover:not(:disabled) {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
  }

  .demo-banner .demo-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .dismiss-button {
    margin-left: auto;
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 1.2rem;
    padding: 0 0.25rem;
    line-height: 1;
  }

  .dismiss-button:hover {
    color: var(--text-primary);
  }

  /* Sections */
  .section {
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    margin-bottom: 1rem;
    overflow: hidden;
  }

  .section-header {
    background: var(--bg-secondary);
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--border-color);
  }

  .section-body {
    padding: var(--space-4);
  }

  /* Drop zone */
  .drop-zone {
    border: 2px dashed var(--border-color);
    border-radius: var(--radius-md);
    padding: 2rem;
    text-align: center;
    transition: border-color 120ms ease-out, background 120ms ease-out;
  }

  .drop-zone.dragging {
    border-color: var(--accent-blue);
    background: rgba(31, 111, 235, 0.05);
  }

  .drop-zone p {
    margin: 0 0 0.75rem 0;
    color: var(--text-secondary);
    font-size: var(--text-sm);
  }

  .choose-file-button {
    display: inline-block;
    padding: 0.4rem 1rem;
    background: var(--bg-hover);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: var(--text-sm);
    color: var(--text-primary);
  }

  .choose-file-button:hover {
    background: var(--border-color);
  }

  .choose-file-button input {
    display: none;
  }

  .file-types {
    display: block;
    margin-top: 0.5rem;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  /* File status line */
  .file-status {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    font-size: var(--text-sm);
  }

  .file-status-check {
    color: var(--color-pass);
    font-weight: 600;
  }

  .file-status-name {
    color: var(--text-primary);
    font-weight: 500;
  }

  .change-button {
    margin-left: auto;
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    padding: 0.2rem 0.6rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: var(--text-xs);
  }

  .change-button:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  /* Server path */
  .method-content input[type="text"] {
    width: 100%;
    box-sizing: border-box;
  }

  .method-content input[type="text"][placeholder*="/path"] {
    font-family: monospace;
    margin-bottom: 0.5rem;
  }

  /* Platform */
  .platform-prompt {
    margin: 0 0 0.75rem 0;
    color: var(--text-secondary);
    font-size: var(--text-sm);
  }

  .api-key-form {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .api-key-input {
    flex: 1;
    font-family: monospace;
  }

  .connected-status {
    margin-bottom: 1rem;
  }

  .connected-badge {
    color: var(--color-pass);
    font-size: var(--text-sm);
    font-weight: 500;
  }

  .loading {
    color: var(--text-secondary);
    font-style: italic;
    font-size: var(--text-sm);
    margin: 0;
  }

  .empty-state {
    color: var(--text-secondary);
    font-style: italic;
    font-size: var(--text-sm);
    padding: 1rem 0;
    margin: 0;
  }

  .agents-list {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .agent-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    cursor: pointer;
    text-align: left;
    transition: background 80ms ease-out, border-color 80ms ease-out;
  }

  .agent-item:hover {
    background: var(--bg-hover);
  }

  .agent-item.selected {
    border-color: var(--accent-blue);
    background: var(--bg-hover);
  }

  .agent-radio {
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  .agent-item.selected .agent-radio {
    color: var(--accent-blue);
  }

  .agent-name {
    font-weight: 500;
    color: var(--text-primary);
    font-size: var(--text-sm);
  }

  .agent-id {
    margin-left: auto;
    font-family: monospace;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }

  /* Method entries */
  .method-entry {
    border: 1px dashed transparent;
    border-radius: var(--radius-md);
    padding: var(--space-3);
    margin-bottom: 2px;
  }

  .method-entry.active {
    border-color: var(--border-color);
    margin-bottom: var(--space-2);
  }

  .method-content {
    padding-top: var(--space-3);
  }

  /* Method toggles */
  .method-toggle {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.35rem 0;
    font-size: var(--text-sm);
    text-align: left;
    width: 100%;
  }

  .method-toggle:hover {
    color: var(--text-primary);
  }

  /* Animated caret */
  .caret {
    display: inline-block;
    transition: transform 150ms ease-out;
    font-size: 0.7em;
  }

  .caret.open {
    transform: rotate(90deg);
  }

  /* Details section */
  .form-row {
    margin-bottom: 0.75rem;
  }

  .form-row label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    font-size: var(--text-sm);
  }

  .form-row input {
    flex: 1;
  }

  .json-editor {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
    font-family: monospace;
    font-size: var(--text-sm);
    margin: 0.5rem 0 0.75rem 0;
  }

  .button-row {
    margin-top: 0.75rem;
  }

  .import-button {
    background: var(--accent);
    color: #ffffff;
    border: 1px solid var(--accent);
    padding: 0.5rem 1.25rem;
    border-radius: var(--radius-md);
    font-weight: 500;
    cursor: pointer;
    font-size: var(--text-sm);
  }

  .import-button:hover:not(:disabled) {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
  }

  .import-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .hint {
    font-size: var(--text-xs);
    color: var(--text-muted);
    margin: 0;
  }

  .error-message {
    color: #f87171;
    background: rgba(248, 113, 113, 0.1);
    border: 1px solid rgba(248, 113, 113, 0.4);
    border-radius: var(--radius-md);
    padding: 0.75rem 1rem;
    margin: 0;
    font-size: var(--text-sm);
  }

  @media (max-width: 480px) {
    .form-row label {
      flex-direction: column;
      align-items: stretch;
      gap: 0.25rem;
    }

    .api-key-form {
      flex-direction: column;
    }

    .drop-zone {
      padding: 1.5rem 1rem;
    }
  }

  .importing-state {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    padding: var(--space-4);
    color: var(--text-secondary);
  }

  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid var(--border-color);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
