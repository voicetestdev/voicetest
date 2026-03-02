<script lang="ts">
  import { currentAgentId, loadAgents } from "../lib/stores";
  import { api } from "../lib/api";
  import SnippetManager from "./SnippetManager.svelte";
  import type { DecompositionResult } from "../lib/types";

  let snippets = $state<Record<string, string>>({});

  let decomposing = $state(false);
  let decomposeResult = $state<DecompositionResult | null>(null);
  let modelOverride = $state("");
  let numAgents = $state(0);
  let showOptions = $state(false);
  let error = $state("");
  let importing = $state(false);
  let importedIds = $state<string[]>([]);

  let expandedSubAgents = $state<Set<string>>(new Set());
  let showManifest = $state(false);

  async function runDecompose() {
    if (!$currentAgentId) return;
    decomposing = true;
    decomposeResult = null;
    importedIds = [];
    error = "";
    try {
      decomposeResult = await api.decomposeAgent(
        $currentAgentId,
        modelOverride || undefined,
        numAgents,
      );
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    decomposing = false;
  }

  async function importSubAgents() {
    if (!decomposeResult) return;
    importing = true;
    error = "";
    const ids: string[] = [];
    try {
      for (const spec of decomposeResult.plan.sub_agents) {
        const graph = decomposeResult.sub_graphs[spec.sub_agent_id];
        if (!graph) continue;
        const agent = await api.createAgent(spec.name, graph);
        ids.push(agent.id);
      }
      importedIds = ids;
      await loadAgents();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    importing = false;
  }

  function downloadFiles() {
    if (!decomposeResult) return;
    for (const spec of decomposeResult.plan.sub_agents) {
      const graph = decomposeResult.sub_graphs[spec.sub_agent_id];
      if (!graph) continue;
      const blob = new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${spec.sub_agent_id}.vt.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
    // Download manifest
    const manifestBlob = new Blob(
      [JSON.stringify(decomposeResult.manifest, null, 2)],
      { type: "application/json" },
    );
    const manifestUrl = URL.createObjectURL(manifestBlob);
    const manifestLink = document.createElement("a");
    manifestLink.href = manifestUrl;
    manifestLink.download = "manifest.json";
    manifestLink.click();
    URL.revokeObjectURL(manifestUrl);
  }

  function toggleSubAgent(id: string) {
    const next = new Set(expandedSubAgents);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    expandedSubAgents = next;
  }

  function handleChildError(msg: string) {
    error = msg;
  }
</script>

<div class="optimize-view">
  <p class="view-intro">
    Optimize your agent's graph for maintainability and modularity.
  </p>

  <!-- Snippets Section -->
  <div class="section">
    <div class="section-header">Snippets (DRY)</div>
    <div class="section-body">
      <p class="section-intro">
        Finds repeated text across your prompts and extracts it into
        reusable {"{%name%}"} references. Change in one place, update everywhere.
      </p>
      {#if $currentAgentId}
        <SnippetManager agentId={$currentAgentId} bind:snippets onerror={handleChildError} />
      {/if}
    </div>
  </div>

  <!-- Decompose Section -->
  <div class="section">
    <div class="section-header">Decompose</div>
    <div class="section-body">
      <p class="section-intro">
        Splits a complex agent into focused sub-agents, each handling
        one concern. Generates handoff rules and an orchestrator manifest
        for modular, testable agents.
      </p>

      <button class="method-toggle" onclick={() => showOptions = !showOptions}>
        <span class="caret" class:open={showOptions}>&#9654;</span> Options
      </button>
      {#if showOptions}
        <div class="decompose-options">
          <label>
            Model:
            <input type="text" bind:value={modelOverride} placeholder="Default (judge model)" />
          </label>
          <label>
            Sub-agents:
            <input type="number" bind:value={numAgents} min="0" placeholder="0 = auto" />
          </label>
        </div>
      {/if}

      <div class="button-row">
        <button class="btn-primary" onclick={runDecompose} disabled={decomposing || !$currentAgentId}>
          {decomposing ? "Decomposing..." : "Decompose Agent"}
        </button>
      </div>

      {#if decomposeResult}
        <div class="decompose-results">
          <h4>Decomposition Plan</h4>
          <p class="rationale">{decomposeResult.plan.rationale}</p>

          <h4>Sub-Agents ({decomposeResult.plan.num_sub_agents})</h4>
          {#each decomposeResult.plan.sub_agents as spec}
            <div class="sub-agent-card">
              <button class="method-toggle" onclick={() => toggleSubAgent(spec.sub_agent_id)}>
                <span class="caret" class:open={expandedSubAgents.has(spec.sub_agent_id)}>&#9654;</span>
                <strong>{spec.name}</strong>
                <span class="sub-agent-meta">{spec.node_ids.length} nodes</span>
              </button>
              <p class="sub-agent-desc">{spec.description}</p>
              {#if expandedSubAgents.has(spec.sub_agent_id)}
                <pre class="json-preview">{JSON.stringify(decomposeResult.sub_graphs[spec.sub_agent_id], null, 2)}</pre>
              {/if}
            </div>
          {/each}

          {#if decomposeResult.plan.handoff_rules.length > 0}
            <h4>Handoff Rules</h4>
            {#each decomposeResult.plan.handoff_rules as rule}
              <div class="handoff-rule">
                <span>{rule.source_sub_agent_id}</span>
                <span class="arrow">&rarr;</span>
                <span>{rule.target_sub_agent_id}</span>
                <span class="rule-condition">{rule.condition}</span>
              </div>
            {/each}
          {/if}

          <button class="method-toggle" onclick={() => showManifest = !showManifest}>
            <span class="caret" class:open={showManifest}>&#9654;</span> Orchestrator Manifest
          </button>
          {#if showManifest}
            <pre class="json-preview">{JSON.stringify(decomposeResult.manifest, null, 2)}</pre>
          {/if}

          <div class="results-actions">
            <button class="btn-primary" onclick={importSubAgents} disabled={importing}>
              {importing ? "Importing..." : "Import as Agents"}
            </button>
            <button onclick={downloadFiles}>Download Files</button>
          </div>

          {#if importedIds.length > 0}
            <p class="success-msg">Imported {importedIds.length} sub-agents.</p>
          {/if}
        </div>
      {/if}
    </div>
  </div>

  {#if error}
    <p class="error-message">{error}</p>
  {/if}
</div>

<style>
  .optimize-view {
    width: 100%;
    overflow-y: auto;
    flex: 1;
  }

  .view-intro {
    color: var(--text-secondary);
    margin: 0 0 1.5rem 0;
    font-size: var(--text-sm);
  }

  .section {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    margin-bottom: 1.5rem;
    overflow: hidden;
  }

  .section-header {
    padding: var(--space-3) var(--space-4);
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-color);
    font-weight: 600;
    font-size: var(--text-sm);
    color: var(--text-primary);
  }

  .section-body {
    padding: var(--space-4);
  }

  .section-intro {
    color: var(--text-secondary);
    font-size: var(--text-sm);
    margin: 0 0 1rem 0;
    line-height: 1.5;
  }

  .method-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.4rem 0;
    font-size: var(--text-sm);
    width: auto;
  }

  .method-toggle:hover {
    color: var(--text-primary);
    background: transparent;
  }

  .caret {
    display: inline-block;
    font-size: 0.65rem;
    transition: transform 150ms ease;
  }

  .caret.open {
    transform: rotate(90deg);
  }

  .decompose-options {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 0.75rem;
    margin: 0.5rem 0;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
  }

  .decompose-options label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: var(--text-sm);
    color: var(--text-secondary);
  }

  .decompose-options input {
    flex: 1;
    max-width: 250px;
  }

  .button-row {
    margin-top: 0.75rem;
  }

  .decompose-results {
    margin-top: 1.25rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .decompose-results h4 {
    margin: 1rem 0 0.5rem;
    font-size: var(--text-sm);
    color: var(--text-primary);
  }

  .decompose-results h4:first-child {
    margin-top: 0;
  }

  .rationale {
    color: var(--text-secondary);
    font-size: var(--text-sm);
    line-height: 1.5;
    margin: 0 0 0.75rem 0;
  }

  .sub-agent-card {
    margin-bottom: 0.75rem;
    padding: 0.75rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
  }

  .sub-agent-meta {
    font-size: var(--text-xs);
    color: var(--text-muted);
    margin-left: auto;
  }

  .sub-agent-desc {
    color: var(--text-secondary);
    font-size: var(--text-sm);
    margin: 0.25rem 0 0 0;
  }

  .json-preview {
    margin: 0.5rem 0 0 0;
    padding: 0.75rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-family: monospace;
    font-size: var(--text-xs);
    color: var(--text-secondary);
    white-space: pre-wrap;
    word-wrap: break-word;
    max-height: 300px;
    overflow-y: auto;
    line-height: 1.4;
  }

  .handoff-rule {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.5rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    color: var(--text-secondary);
    flex-wrap: wrap;
  }

  .arrow {
    color: var(--text-muted);
  }

  .rule-condition {
    font-size: var(--text-xs);
    color: var(--text-muted);
    margin-left: auto;
  }

  .results-actions {
    display: flex;
    gap: 0.75rem;
    margin-top: 1rem;
  }

  .success-msg {
    color: var(--color-pass);
    font-size: var(--text-sm);
    margin: 0.75rem 0 0 0;
  }

  .error-message {
    color: #f87171;
    background: rgba(248, 113, 113, 0.1);
    border: 1px solid rgba(248, 113, 113, 0.4);
    border-radius: var(--radius-md);
    padding: 0.75rem 1rem;
    margin: 0 0 1rem 0;
    font-size: var(--text-sm);
  }
</style>
