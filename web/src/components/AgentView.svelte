<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
    currentAgentId,
    currentAgent,
    loadAgents,
    currentView,
  } from "../lib/stores";
  import type { ExporterInfo } from "../lib/types";

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

  $effect(() => {
    api.listExporters().then((list) => {
      exporters = list;
    });
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
    } catch (e) {
      console.error("Failed to render graph:", e);
    }
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
        </div>
      </div>
    {/if}

    <section class="graph-section">
      <h3>Agent Graph</h3>
      <div class="mermaid-container">
        {@html mermaidSvg}
      </div>
    </section>

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
    max-width: 500px;
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
  }
</style>
