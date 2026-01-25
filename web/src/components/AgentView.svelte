<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
    currentAgentId,
    currentAgent,
    loadAgents,
    currentView,
  } from "../lib/stores";
  import type { ExporterInfo, Platform, PlatformStatus } from "../lib/types";

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
  let tooltip = $state({ show: false, x: 0, y: 0, text: "" });

  let retellStatus = $state<PlatformStatus | null>(null);
  let vapiStatus = $state<PlatformStatus | null>(null);
  let apiKeyInput = $state("");
  let configuringPlatform = $state(false);
  let exportingToPlatform = $state(false);
  let exportSuccess = $state<{ platform: string; id: string; name: string } | null>(null);

  $effect(() => {
    api.listExporters().then((list) => {
      exporters = list;
    });
  });

  $effect(() => {
    if (showExportModal) {
      api.getPlatformStatus("retell").then((s) => (retellStatus = s)).catch(() => {});
      api.getPlatformStatus("vapi").then((s) => (vapiStatus = s)).catch(() => {});
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
    const nodes = mermaidContainer.querySelectorAll(".node");
    nodes.forEach((node) => {
      const textEl = node.querySelector(".nodeLabel");
      if (!textEl) return;
      const nodeId = node.id?.replace(/^flowchart-/, "").split("-")[0];
      if (!nodeId || !$agentGraph?.nodes[nodeId]) return;

      node.addEventListener("mouseenter", (e) => {
        const rect = (e.target as Element).getBoundingClientRect();
        const instructions = $agentGraph?.nodes[nodeId]?.instructions || "";
        tooltip = {
          show: true,
          x: rect.left + rect.width / 2,
          y: rect.top - 8,
          text: instructions,
        };
      });
      node.addEventListener("mouseleave", () => {
        tooltip = { ...tooltip, show: false };
      });
    });
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
      if (platform === "retell") {
        retellStatus = status;
      } else {
        vapiStatus = status;
      }
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
  }

  function getPlatformStatus(platform: Platform): PlatformStatus | null {
    return platform === "retell" ? retellStatus : vapiStatus;
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="agent-view">
  {#if !$agentGraph || !$currentAgent}
    <p class="placeholder">No agent selected.</p>
  {:else}
    <h2>{$currentAgent.name}</h2>

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
                <p>Agent created in {exportSuccess.platform === "retell" ? "Retell" : "VAPI"}!</p>
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

                {#each ["retell", "vapi"] as platform}
                  {@const status = getPlatformStatus(platform as Platform)}
                  {@const platformName = platform === "retell" ? "Retell" : "VAPI"}
                  <div class="platform-export-row">
                    {#if !status?.configured}
                      <div class="platform-setup">
                        <span class="platform-label">{platformName}</span>
                        <input
                          type="password"
                          bind:value={apiKeyInput}
                          placeholder="API Key"
                          class="api-key-input-small"
                        />
                        <button
                          onclick={() => configureAndExport(platform as Platform)}
                          disabled={configuringPlatform || exportingToPlatform || !apiKeyInput.trim()}
                        >
                          {configuringPlatform || exportingToPlatform ? "..." : "Connect & Export"}
                        </button>
                      </div>
                    {:else}
                      <div class="platform-configured">
                        <span class="platform-label">{platformName}</span>
                        <span class="connected-badge-small">Connected</span>
                        <button
                          class="platform-export-btn"
                          onclick={() => exportToPlatform(platform as Platform)}
                          disabled={exportingToPlatform}
                        >
                          {exportingToPlatform ? "Creating..." : `Create in ${platformName}`}
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
      <h3>Agent Graph</h3>
      <div class="mermaid-container" bind:this={mermaidContainer}>
        {@html mermaidSvg}
      </div>
    </section>

    {#if tooltip.show}
      <div
        class="node-tooltip"
        style="left: {tooltip.x}px; top: {tooltip.y}px;"
      >
        {tooltip.text}
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
    background: var(--bg-hover);
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
  }

  .agent-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }

  .info-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .label {
    color: var(--text-secondary);
    min-width: 100px;
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
    border-radius: 8px;
    margin-bottom: 1rem;
  }

  .mermaid-container {
    overflow: auto;
  }

  .mermaid-container :global(svg) {
    max-width: 100%;
    height: auto;
  }

  .mermaid-container :global(.node) {
    cursor: pointer;
  }

  .node-tooltip {
    position: fixed;
    transform: translate(-50%, -100%);
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 0.75rem;
    max-width: 400px;
    max-height: 200px;
    overflow-y: auto;
    font-size: 0.85rem;
    line-height: 1.4;
    white-space: pre-wrap;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    z-index: 100;
    pointer-events: none;
  }

  .danger-zone {
    background: var(--bg-tertiary);
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid #7f1d1d;
  }

  .danger {
    background: var(--danger-bg);
    color: var(--danger-text);
  }

  .danger:hover {
    background: var(--danger-bg-hover);
  }

  .export-btn.primary {
    background: #2563eb;
    padding: 0.6rem 1.2rem;
  }

  .export-btn.primary:hover {
    background: #1d4ed8;
  }

  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: var(--bg-tertiary);
    border-radius: 12px;
    min-width: 400px;
    max-width: 550px;
    max-height: 80vh;
    overflow: hidden;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h3 {
    margin: 0;
    color: var(--text-primary);
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
  }

  .modal-body {
    padding: 1rem;
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
    padding: 1rem;
    background: var(--bg-hover);
    border-radius: 8px;
    text-align: left;
    cursor: pointer;
    transition: background 0.15s;
  }

  .export-option:hover {
    background: var(--border-color);
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
