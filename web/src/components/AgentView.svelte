<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
    currentAgentId,
    currentAgent,
    loadAgents,
    currentView,
  } from "../lib/stores";
  import type { ExporterInfo, Platform, PlatformInfo, PlatformStatus } from "../lib/types";

  interface Props {
    theme?: "light" | "dark";
  }

  let { theme = "dark" }: Props = $props();

  let error = $state("");
  let mermaidSvg = $state("");
  let exporters = $state<ExporterInfo[]>([]);
  let exporting = $state(false);
  let showExportModal = $state(false);
  let lastGraphId = $state<string | null>(null);
  let lastTheme = $state<string | null>(null);
  let renderCounter = 0;
  let mermaidContainer: HTMLDivElement;
  let tooltip = $state({ show: false, x: 0, y: 0, text: "", title: "" });
  let zoomLevel = $state(1);

  let platforms = $state<PlatformInfo[]>([]);
  let platformStatus = $state<Record<string, PlatformStatus>>({});
  let apiKeyInput = $state("");
  let configuringPlatform = $state(false);
  let exportingToPlatform = $state(false);
  let exportSuccess = $state<{ platform: string; id: string; name: string } | null>(null);

  let editingName = $state(false);
  let editedName = $state("");
  let savingName = $state(false);
  let nameSaved = $state(false);
  let nameInput: HTMLInputElement;

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
    api.listExporters().then((list) => {
      exporters = list;
    });
  });

  $effect(() => {
    if (showExportModal) {
      api.listPlatforms().then((list) => {
        platforms = list;
        for (const p of list) {
          platformStatus[p.name] = { platform: p.name, configured: p.configured };
        }
      }).catch(() => {});
      exportSuccess = null;
    }
  });

  $effect(() => {
    const graph = $agentGraph;
    const graphId = graph ? `${graph.entry_node_id}-${Object.keys(graph.nodes).length}` : null;
    const currentTheme = theme;

    if (graphId && (graphId !== lastGraphId || currentTheme !== lastTheme)) {
      lastGraphId = graphId;
      lastTheme = currentTheme;
      renderGraph(graph, currentTheme);
    } else if (!graph) {
      mermaidSvg = "";
      lastGraphId = null;
    }
  });

  async function renderGraph(graph: typeof $agentGraph, currentTheme: "light" | "dark") {
    if (!graph) return;
    const currentRender = ++renderCounter;
    try {
      const result = await api.exportAgent(graph, "mermaid");
      if (currentRender !== renderCounter) return; // Stale render
      const mermaid = await import("mermaid");
      const mermaidTheme = currentTheme === "light" ? "default" : "dark";
      mermaid.default.initialize({
        startOnLoad: false,
        theme: mermaidTheme,
        themeVariables: currentTheme === "light" ? {
          primaryColor: "#dbeafe",
          primaryTextColor: "#1e3a8a",
          primaryBorderColor: "#3b82f6",
          lineColor: "#6b7280",
          secondaryColor: "#f3f4f6",
          tertiaryColor: "#ecfdf5",
          tertiaryTextColor: "#065f46",
        } : {
          primaryColor: "#1e3a5f",
          primaryTextColor: "#e0f2fe",
          primaryBorderColor: "#3b82f6",
          lineColor: "#9ca3af",
          secondaryColor: "#374151",
          tertiaryColor: "#166534",
          tertiaryTextColor: "#ffffff",
        },
      });
      const renderId = `agent-graph-${currentRender}`;
      const { svg } = await mermaid.default.render(renderId, result.content);
      if (currentRender !== renderCounter) return; // Stale render
      mermaidSvg = svg;
      // Setup tooltips after DOM update
      requestAnimationFrame(() => setupTooltips());
    } catch (e) {
      console.error("Failed to render graph:", e);
    }
  }

  function setupTooltips() {
    if (!mermaidContainer || !$agentGraph) return;

    // Build a map of known node IDs for matching
    const knownNodeIds = new Set(Object.keys($agentGraph.nodes));

    // Setup node tooltips
    const nodes = mermaidContainer.querySelectorAll(".node");
    nodes.forEach((node) => {
      const textEl = node.querySelector(".nodeLabel");
      if (!textEl) return;

      // Extract node ID from the label text (format: "node_id<br/>...")
      const labelText = textEl.textContent || "";
      const nodeId = labelText.split(/\s/)[0]; // First word is the node ID

      // Try to find matching node - check exact match first, then prefix match
      let matchedId: string | null = null;
      if (knownNodeIds.has(nodeId)) {
        matchedId = nodeId;
      } else {
        // Try to match by checking if any known ID is a prefix
        for (const knownId of knownNodeIds) {
          if (labelText.startsWith(knownId)) {
            matchedId = knownId;
            break;
          }
        }
      }

      if (!matchedId) return;
      const nodeData = $agentGraph?.nodes[matchedId];
      if (!nodeData) return;

      node.addEventListener("mouseenter", (e) => {
        const rect = (e.target as Element).getBoundingClientRect();
        tooltip = {
          show: true,
          x: rect.left + rect.width / 2,
          y: rect.top - 8,
          title: matchedId,
          text: nodeData.instructions,
        };
      });
      node.addEventListener("mouseleave", () => {
        tooltip = { ...tooltip, show: false };
      });
    });

    // Setup edge label tooltips
    const edgeLabels = mermaidContainer.querySelectorAll(".edgeLabel");
    edgeLabels.forEach((label) => {
      const labelText = label.textContent?.trim() || "";
      if (!labelText) return;

      // Find the full transition condition by matching truncated text
      let fullCondition = labelText;
      for (const node of Object.values($agentGraph?.nodes || {})) {
        for (const transition of node.transitions) {
          const condValue = transition.condition.value;
          if (condValue.startsWith(labelText.replace("...", "")) ||
              labelText.replace("...", "") === condValue.slice(0, labelText.length - 3)) {
            fullCondition = condValue;
            break;
          }
        }
      }

      label.addEventListener("mouseenter", (e) => {
        const rect = (e.target as Element).getBoundingClientRect();
        tooltip = {
          show: true,
          x: rect.left + rect.width / 2,
          y: rect.top - 8,
          title: "Transition",
          text: fullCondition,
        };
      });
      label.addEventListener("mouseleave", () => {
        tooltip = { ...tooltip, show: false };
      });
    });
  }

  function zoomIn() {
    zoomLevel = Math.min(zoomLevel + 0.25, 3);
  }

  function zoomOut() {
    zoomLevel = Math.max(zoomLevel - 0.25, 0.25);
  }

  function resetZoom() {
    zoomLevel = 1;
  }

  function getExportFilename(exp: ExporterInfo): string {
    const agentName = $currentAgent?.name || "agent";
    const safeName = agentName.replace(/[^a-zA-Z0-9_-]/g, "_");
    const suffix = exp.id.replace(/-/g, "_");
    return `${safeName}_${suffix}.${exp.ext}`;
  }

  async function exportTo(exp: ExporterInfo) {
    if (!$agentGraph) return;
    exporting = true;
    error = "";
    try {
      const result = await api.exportAgent($agentGraph, exp.id);
      const blob = new Blob([result.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = getExportFilename(exp);
      a.click();
      URL.revokeObjectURL(url);
      showExportModal = false;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    exporting = false;
  }

  async function exportToPlatform(platform: Platform) {
    if (!$agentGraph) return;
    exportingToPlatform = true;
    error = "";
    try {
      const name = $currentAgent?.name;
      const result = await api.exportToPlatform(platform, $agentGraph, name);
      exportSuccess = {
        platform: result.platform,
        id: result.id,
        name: result.name,
      };
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    exportingToPlatform = false;
  }

  async function configureAndExport(platform: Platform) {
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
      await exportToPlatform(platform);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    configuringPlatform = false;
  }

  async function deleteCurrentAgent() {
    if (!$currentAgentId) return;
    if (!confirm("Are you sure you want to delete this agent?")) return;
    try {
      await api.deleteAgent($currentAgentId);
      await loadAgents();
      agentGraph.set(null);
      currentAgentId.set(null);
      currentView.set("import");
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  function closeModal(e: MouseEvent) {
    if ((e.target as HTMLElement).classList.contains("modal-backdrop")) {
      showExportModal = false;
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape" && showExportModal) {
      showExportModal = false;
    }
    if (e.key === "Escape" && editingName) {
      editingName = false;
    }
  }

  function startEditingName() {
    editedName = $currentAgent?.name || "";
    editingName = true;
    requestAnimationFrame(() => {
      nameInput?.focus();
      nameInput?.select();
    });
  }

  async function saveName() {
    if (!$currentAgentId || !editedName.trim()) {
      editingName = false;
      return;
    }
    if (editedName.trim() === $currentAgent?.name) {
      editingName = false;
      return;
    }
    savingName = true;
    try {
      await api.updateAgent($currentAgentId, editedName.trim());
      await loadAgents();
      editingName = false;
      nameSaved = true;
      setTimeout(() => { nameSaved = false; }, 2000);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    savingName = false;
  }

  function handleNameKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") {
      saveName();
    }
  }

</script>

<svelte:window onkeydown={handleKeydown} />

<div class="agent-view">
  {#if !$agentGraph || !$currentAgent}
    <p class="placeholder">No agent selected.</p>
  {:else}
    <div class="name-row">
      {#if editingName}
        <input
          type="text"
          class="name-input"
          bind:value={editedName}
          bind:this={nameInput}
          onblur={saveName}
          onkeydown={handleNameKeydown}
          disabled={savingName}
        />
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
        <h2 class="editable-name" onclick={startEditingName} title="Click to edit">
          {$currentAgent.name}
        </h2>
      {/if}
      {#if savingName}
        <span class="save-indicator">Saving...</span>
      {:else if nameSaved}
        <span class="save-indicator saved">Saved</span>
      {/if}
    </div>

    <section class="agent-info">
      <div class="info-row">
        <span class="label">Source:</span>
        <span class="tag">{$agentGraph.source_type}</span>
      </div>
      <div class="info-row">
        <span class="label">Entry Node:</span>
        <span>{$agentGraph.entry_node_id}</span>
      </div>
      <div class="info-row">
        <span class="label">Nodes:</span>
        <span>{Object.keys($agentGraph.nodes).length}</span>
      </div>
      {#if $currentAgent.source_path}
        <div class="info-row">
          <span class="label">Linked File:</span>
          <span class="mono">{$currentAgent.source_path}</span>
        </div>
      {/if}
    </section>

    <div class="actions">
      <button
        class="export-btn primary"
        onclick={() => (showExportModal = true)}
        disabled={exporting}
      >
        Export Agent...
      </button>
    </div>
    {#if error}
      <p class="error-message">{error}</p>
    {/if}

    {#if showExportModal}
      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
      <div class="modal-backdrop" onclick={closeModal}>
        <div class="modal">
          <div class="modal-header">
            <h3>Export Agent</h3>
            <button class="close-btn" onclick={() => (showExportModal = false)}>&times;</button>
          </div>
          <div class="modal-body">
            {#if exportSuccess}
              <div class="export-success">
                <div class="success-icon">&#10003;</div>
                <p>Agent created in {getPlatformDisplayName(exportSuccess.platform)}!</p>
                <p class="success-details">
                  <strong>{exportSuccess.name}</strong><br />
                  <span class="mono">{exportSuccess.id}</span>
                </p>
                <button onclick={() => (exportSuccess = null)}>Export Another</button>
              </div>
            {:else}
              <div class="export-section">
                <h4>Download as File</h4>
                <div class="export-options">
                  {#each exporters as exp}
                    <button
                      class="export-option"
                      onclick={() => exportTo(exp)}
                      disabled={exporting}
                    >
                      <span class="export-name">{exp.name}</span>
                      <span class="export-desc">{exp.description}</span>
                      <span class="export-ext">.{exp.ext}</span>
                    </button>
                  {/each}
                </div>
              </div>

              <div class="divider">or</div>

              <div class="export-section">
                <h4>Export to Platform</h4>

                {#each platforms as platform}
                  {@const status = platformStatus[platform.name]}
                  {@const displayName = getPlatformDisplayName(platform.name)}
                  <div class="platform-export-row">
                    {#if !status?.configured}
                      <div class="platform-setup">
                        <span class="platform-label">{displayName}</span>
                        <input
                          type="password"
                          bind:value={apiKeyInput}
                          placeholder="API Key"
                          class="api-key-input-small"
                        />
                        <button
                          onclick={() => configureAndExport(platform.name)}
                          disabled={configuringPlatform || exportingToPlatform || !apiKeyInput.trim()}
                        >
                          {configuringPlatform || exportingToPlatform ? "..." : "Connect & Export"}
                        </button>
                      </div>
                    {:else}
                      <div class="platform-configured">
                        <span class="platform-label">{displayName}</span>
                        <span class="connected-badge-small">Connected</span>
                        <button
                          class="platform-export-btn"
                          onclick={() => exportToPlatform(platform.name)}
                          disabled={exportingToPlatform}
                        >
                          {exportingToPlatform ? "Creating..." : `Create in ${displayName}`}
                        </button>
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>

              {#if error}
                <p class="modal-error">{error}</p>
              {/if}
            {/if}
          </div>
        </div>
      </div>
    {/if}

    <section class="graph-section">
      <div class="graph-header">
        <h3>Agent Graph</h3>
        <div class="zoom-controls">
          <button onclick={zoomOut} title="Zoom out">−</button>
          <span class="zoom-level">{Math.round(zoomLevel * 100)}%</span>
          <button onclick={zoomIn} title="Zoom in">+</button>
          <button onclick={resetZoom} title="Reset zoom">Reset</button>
        </div>
      </div>
      <div class="mermaid-container" bind:this={mermaidContainer}>
        <div class="mermaid-content" style="transform: scale({zoomLevel}); transform-origin: top left;">
          {@html mermaidSvg}
        </div>
      </div>
    </section>

    {#if tooltip.show}
      <div
        class="node-tooltip"
        style="left: {tooltip.x}px; top: {tooltip.y}px;"
      >
        {#if tooltip.title}
          <div class="tooltip-title">{tooltip.title}</div>
        {/if}
        <div class="tooltip-text">{tooltip.text}</div>
      </div>
    {/if}

    <section class="danger-zone">
      <h3>Danger Zone</h3>
      <button class="danger" onclick={deleteCurrentAgent}>
        Delete Agent
      </button>
    </section>
  {/if}
</div>

<style>
  .agent-view {
    width: 100%;
    overflow-y: auto;
    flex: 1;
  }

  h2 {
    margin-top: 0;
  }

  .name-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .editable-name {
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    margin: -0.25rem -0.5rem;
    border-radius: 4px;
    transition: background 0.15s;
  }

  .editable-name:hover {
    background: var(--bg-hover);
  }

  .name-input {
    font-size: 1.5rem;
    font-weight: bold;
    padding: 0.25rem 0.5rem;
    border: 1px solid var(--accent-color, #6366f1);
    border-radius: 4px;
    background: var(--bg-secondary);
    color: var(--text-primary);
    outline: none;
    min-width: 200px;
  }

  .save-indicator {
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .save-indicator.saved {
    color: #22c55e;
  }

  h3 {
    margin-top: 0;
    font-size: 1rem;
    color: var(--text-secondary);
  }

  h4 {
    margin: 0 0 0.75rem 0;
    font-size: 0.9rem;
    color: var(--text-secondary);
    font-weight: 500;
  }

  .placeholder {
    color: var(--text-secondary);
    font-style: italic;
  }

  .tag {
    background: var(--bg-tertiary);
    padding: 0.2rem 0.5rem;
    border-radius: var(--radius-sm);
    font-size: var(--text-xs);
    border: 1px solid var(--border-color);
  }

  .agent-info {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--space-2) var(--space-4);
    margin-bottom: 1.5rem;
    padding: var(--space-4);
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
  }

  .info-row {
    display: contents;
  }

  .label {
    color: var(--text-secondary);
    font-size: var(--text-sm);
  }

  .mono {
    font-family: monospace;
    font-size: 0.85rem;
  }

  .actions {
    margin-bottom: 1rem;
  }

  .export-btn {
    background: var(--bg-hover);
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
  }

  .export-btn:hover {
    background: var(--border-color);
  }

  .export-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .error-message {
    color: #f87171;
    margin: 0 0 1rem 0;
  }

  .graph-section {
    background: var(--bg-secondary);
    padding: 1rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    margin-bottom: 1rem;
  }

  .graph-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .graph-header h3 {
    margin: 0;
  }

  .zoom-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .zoom-controls button {
    padding: 0.25rem 0.5rem;
    font-size: 0.85rem;
    min-width: 2rem;
  }

  .zoom-level {
    font-size: 0.8rem;
    color: var(--text-secondary);
    min-width: 3rem;
    text-align: center;
  }

  .mermaid-container {
    overflow: auto;
    max-height: 600px;
  }

  .mermaid-content {
    display: inline-block;
    min-width: 100%;
  }

  .mermaid-content :global(svg) {
    display: block;
  }

  .mermaid-container :global(.node) {
    cursor: pointer;
  }

  .mermaid-container :global(.edgeLabel) {
    cursor: pointer;
  }

  .node-tooltip {
    position: fixed;
    transform: translate(-50%, -100%);
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 0.75rem;
    max-width: 500px;
    max-height: 400px;
    overflow-y: auto;
    font-size: 0.85rem;
    line-height: 1.4;
    white-space: pre-wrap;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    z-index: 100;
    pointer-events: none;
  }

  .tooltip-title {
    font-weight: 600;
    margin-bottom: 0.5rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
    color: var(--text-primary);
  }

  .tooltip-text {
    color: var(--text-secondary);
  }

  .danger-zone {
    background: var(--bg-secondary);
    padding: var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--danger-border);
  }

  .danger-zone h3 {
    color: var(--danger-text);
  }

  .danger {
    background: transparent;
    color: var(--danger-text);
    border: 1px solid var(--border-color);
  }

  .danger:hover {
    background: var(--danger-bg-hover);
    border-color: var(--danger-border);
  }

  .export-btn.primary {
    background: var(--accent);
    color: #ffffff;
    border-color: var(--accent);
    padding: 0.6rem 1.2rem;
  }

  .export-btn.primary:hover {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
  }

  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    min-width: 400px;
    max-width: 550px;
    max-height: 80vh;
    overflow: hidden;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-4);
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-tertiary);
  }

  .modal-header h3 {
    margin: 0;
    color: var(--text-primary);
    font-size: var(--text-sm);
  }

  .close-btn {
    background: transparent;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0;
    line-height: 1;
  }

  .close-btn:hover {
    color: var(--text-primary);
    background: transparent;
  }

  .modal-body {
    padding: var(--space-4);
    overflow-y: auto;
    max-height: calc(80vh - 60px);
  }

  .export-section {
    margin-bottom: 1rem;
  }

  .export-options {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .export-option {
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-rows: auto auto;
    gap: 0.25rem 1rem;
    padding: var(--space-3);
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    text-align: left;
    cursor: pointer;
    transition: background 80ms ease-out, border-color 80ms ease-out;
  }

  .export-option:hover {
    background: var(--bg-hover);
    border-color: var(--text-muted);
  }

  .export-option:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .export-name {
    font-weight: 600;
    color: var(--text-primary);
    grid-column: 1;
    grid-row: 1;
  }

  .export-desc {
    color: var(--text-secondary);
    font-size: 0.85rem;
    grid-column: 1;
    grid-row: 2;
  }

  .export-ext {
    color: var(--text-muted);
    font-family: monospace;
    font-size: 0.8rem;
    grid-column: 2;
    grid-row: 1 / 3;
    align-self: center;
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

  .platform-export-row {
    margin-bottom: 0.75rem;
  }

  .platform-setup,
  .platform-configured {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .platform-label {
    font-weight: 500;
    min-width: 50px;
  }

  .api-key-input-small {
    flex: 1;
    min-width: 120px;
    padding: 0.4rem 0.6rem;
    font-size: 0.85rem;
    font-family: monospace;
  }

  .connected-badge-small {
    background: #166534;
    color: white;
    padding: 0.2rem 0.5rem;
    border-radius: 9999px;
    font-size: 0.7rem;
    font-weight: 500;
  }

  .platform-export-btn {
    margin-left: auto;
  }

  .modal-error {
    color: #f87171;
    margin: 1rem 0 0 0;
    font-size: 0.85rem;
  }

  .export-success {
    text-align: center;
    padding: 1rem;
  }

  .success-icon {
    width: 48px;
    height: 48px;
    background: #166534;
    color: white;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    margin-bottom: 1rem;
  }

  .export-success p {
    margin: 0 0 0.5rem 0;
  }

  .success-details {
    background: var(--bg-hover);
    padding: 0.75rem;
    border-radius: 6px;
    margin-bottom: 1rem;
  }

  .success-details .mono {
    font-size: 0.8rem;
    color: var(--text-muted);
  }

  @media (max-width: 768px) {
    .modal {
      min-width: unset;
      max-width: unset;
      width: calc(100% - 2rem);
      margin: 1rem;
    }

    .export-option {
      padding: 0.75rem;
    }

    .platform-setup,
    .platform-configured {
      flex-direction: column;
      align-items: stretch;
    }

    .platform-export-btn {
      margin-left: 0;
    }
  }
</style>
