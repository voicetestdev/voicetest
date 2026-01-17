<script lang="ts">
  import { api } from "../lib/api";
  import { agentGraph } from "../lib/stores";
  import type { ExporterInfo, ImporterInfo } from "../lib/types";

  let configText = $state("");
  let importing = $state(false);
  let error = $state("");
  let mermaidSvg = $state("");
  let importers = $state<ImporterInfo[]>([]);
  let exporters = $state<ExporterInfo[]>([]);
  let exporting = $state(false);

  $effect(() => {
    api.listImporters().then((list) => {
      importers = list;
    });
    api.listExporters().then((list) => {
      exporters = list;
    });
  });

  $effect(() => {
    if ($agentGraph) {
      renderGraph();
    }
  });

  async function importFromText() {
    importing = true;
    error = "";
    try {
      const config = JSON.parse(configText);
      const graph = await api.importAgent(config);
      agentGraph.set(graph);
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
  }

  async function renderGraph() {
    if (!$agentGraph) return;
    try {
      const result = await api.exportAgent($agentGraph, "mermaid");
      const mermaid = await import("mermaid");
      mermaid.default.initialize({ startOnLoad: false, theme: "dark" });
      const { svg } = await mermaid.default.render("agent-graph", result.content);
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
      const ext = format.includes("retell") ? "json" : format === "livekit" ? "py" : "md";
      a.download = `agent-export.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    exporting = false;
  }
</script>

<div class="agent-view">
  <h2>Agent</h2>

  {#if !$agentGraph}
    <section class="import-section">
      <h3>Import Agent</h3>

      <div class="importers">
        <span>Supported formats:</span>
        {#each importers as imp}
          <span class="tag">{imp.source_type}</span>
        {/each}
      </div>

      <div class="import-options">
        <label class="file-upload">
          <input type="file" accept=".json" onchange={handleFile} />
          Upload JSON
        </label>
      </div>

      <textarea
        bind:value={configText}
        placeholder="Or paste agent config JSON here..."
        rows={12}
      ></textarea>

      <button onclick={importFromText} disabled={importing || !configText}>
        {importing ? "Importing..." : "Import Agent"}
      </button>

      {#if error}
        <p class="error-message">{error}</p>
      {/if}
    </section>
  {:else}
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

      <div class="actions-row">
        <button class="secondary" onclick={() => agentGraph.set(null)}>
          Clear Agent
        </button>
      </div>
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
  {/if}
</div>

<style>
  .agent-view {
    max-width: 900px;
  }

  h2 {
    margin-top: 0;
  }

  h3 {
    margin-top: 0;
    font-size: 1rem;
    color: #9ca3af;
  }

  .import-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .importers {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: #9ca3af;
  }

  .tag {
    background: #374151;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
  }

  .import-options {
    display: flex;
    gap: 1rem;
  }

  .file-upload {
    display: inline-block;
    padding: 0.5rem 1rem;
    background: #374151;
    border-radius: 4px;
    cursor: pointer;
  }

  .file-upload:hover {
    background: #4b5563;
  }

  .file-upload input {
    display: none;
  }

  textarea {
    width: 100%;
    resize: vertical;
    font-family: monospace;
  }

  .error-message {
    color: #f87171;
    margin: 0;
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

  .actions-row {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .secondary {
    background: #374151;
  }

  .secondary:hover {
    background: #4b5563;
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

  .graph-section {
    background: #16213e;
    padding: 1rem;
    border-radius: 8px;
  }

  .mermaid-container {
    overflow: auto;
  }

  .mermaid-container :global(svg) {
    max-width: 100%;
    height: auto;
  }
</style>
