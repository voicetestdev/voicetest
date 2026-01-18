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

  let error = $state("");
  let mermaidSvg = $state("");
  let exporters = $state<ExporterInfo[]>([]);
  let exporting = $state(false);
  let lastGraphId = $state<string | null>(null);
  let renderCounter = 0;

  $effect(() => {
    api.listExporters().then((list) => {
      exporters = list;
    });
  });

  $effect(() => {
    const graph = $agentGraph;
    const graphId = graph ? `${graph.entry_node_id}-${Object.keys(graph.nodes).length}` : null;

    if (graphId && graphId !== lastGraphId) {
      lastGraphId = graphId;
      renderGraph(graph);
    } else if (!graph) {
      mermaidSvg = "";
      lastGraphId = null;
    }
  });

  async function renderGraph(graph: typeof $agentGraph) {
    if (!graph) return;
    const currentRender = ++renderCounter;
    try {
      const result = await api.exportAgent(graph, "mermaid");
      if (currentRender !== renderCounter) return; // Stale render
      const mermaid = await import("mermaid");
      mermaid.default.initialize({ startOnLoad: false, theme: "dark" });
      const renderId = `agent-graph-${currentRender}`;
      const { svg } = await mermaid.default.render(renderId, result.content);
      if (currentRender !== renderCounter) return; // Stale render
      mermaidSvg = svg;
    } catch (e) {
      console.error("Failed to render graph:", e);
    }
  }

  async function exportTo(format: string) {
    if (!$agentGraph) return;
    exporting = true;
    error = "";
    try {
      const result = await api.exportAgent($agentGraph, format);
      const blob = new Blob([result.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const ext = format.includes("retell")
        ? "json"
        : format === "livekit"
          ? "py"
          : "md";
      a.download = `agent-export.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
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
</script>

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

    <section class="export-section">
      <h3>Export</h3>
      <div class="export-buttons">
        {#each exporters as exp}
          <button
            class="export-btn"
            onclick={() => exportTo(exp.id)}
            disabled={exporting}
            title={exp.description}
          >
            {exp.name}
          </button>
        {/each}
      </div>
      {#if error}
        <p class="error-message">{error}</p>
      {/if}
    </section>

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
    color: #9ca3af;
  }

  .placeholder {
    color: #9ca3af;
    font-style: italic;
  }

  .tag {
    background: #374151;
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
    color: #9ca3af;
    min-width: 100px;
  }

  .mono {
    font-family: monospace;
    font-size: 0.85rem;
  }

  .export-section {
    background: #1f2937;
    padding: 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
  }

  .export-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .export-btn {
    background: #374151;
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
  }

  .export-btn:hover {
    background: #4b5563;
  }

  .export-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .error-message {
    color: #f87171;
    margin: 0.5rem 0 0 0;
  }

  .graph-section {
    background: #16213e;
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
    background: #1f2937;
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid #7f1d1d;
  }

  .danger {
    background: #dc2626;
  }

  .danger:hover {
    background: #b91c1c;
  }
</style>
