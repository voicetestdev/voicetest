<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
    currentAgentId,
    currentAgent,
    loadAgents,
    refreshAgent,
    currentView,
  } from "../lib/stores";
  import type { SyncStatus } from "../lib/types";
  import CallView from "./CallView.svelte";
  import ChatView from "./ChatView.svelte";
  import ExportModal from "./ExportModal.svelte";
  import SnippetManager from "./SnippetManager.svelte";
  import MetadataEditor from "./MetadataEditor.svelte";
  import NodePromptModal from "./NodePromptModal.svelte";
  import TransitionModal from "./TransitionModal.svelte";

  interface Props {
    theme?: "light" | "dark";
  }

  let { theme = "dark" }: Props = $props();

  let error = $state("");
  let mermaidSvg = $state("");
  let showExportModal = $state(false);
  let lastGraphId = $state<string | null>(null);
  let lastTheme = $state<string | null>(null);
  let renderCounter = 0;
  let mermaidContainer: HTMLDivElement;
  let tooltip = $state({ show: false, x: 0, y: 0, text: "", title: "", nodeId: "", sourceNodeId: "", targetNodeId: "" });
  let tooltipHideTimer: ReturnType<typeof setTimeout> | null = null;
  const TOOLTIP_HIDE_DELAY = 200;
  let zoomLevel = $state(1);
  let panX = $state(0);
  let panY = $state(0);
  let isPanning = $state(false);
  let panStart = { x: 0, y: 0, panX: 0, panY: 0 };
  let touchState = { distance: 0, centerX: 0, centerY: 0, initialZoom: 1, initialPanX: 0, initialPanY: 0 };

  let editingName = $state(false);
  let editedName = $state("");
  let savingName = $state(false);
  let nameSaved = $state(false);
  let nameInput: HTMLInputElement;

  let editingModel = $state(false);
  let editedModel = $state("");
  let savingModel = $state(false);
  let modelSaved = $state(false);
  let modelInput: HTMLInputElement;

  let editingGeneralPrompt = $state(false);
  let editedGeneralPrompt = $state("");
  let savingGeneralPrompt = $state(false);
  let generalPromptSaved = $state(false);
  let generalPromptTextarea: HTMLTextAreaElement;

  let refreshing = $state(false);

  let syncStatus = $state<SyncStatus | null>(null);
  let syncing = $state(false);
  let syncSuccess = $state(false);
  let syncError = $state("");

  let snippets = $state<Record<string, string>>({});

  // Child component refs
  let nodePromptModal: NodePromptModal;
  let transitionModal: TransitionModal;

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

  $effect(() => {
    const agentId = $currentAgentId;
    if (agentId) {
      syncStatus = null;
      syncSuccess = false;
      syncError = "";
      api.getSyncStatus(agentId).then((status) => {
        syncStatus = status;
      }).catch(() => {
        syncStatus = null;
      });
    } else {
      syncStatus = null;
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

  function showTooltip(x: number, y: number, title: string, text: string, opts: { nodeId?: string; sourceNodeId?: string; targetNodeId?: string } = {}) {
    if (tooltipHideTimer) {
      clearTimeout(tooltipHideTimer);
      tooltipHideTimer = null;
    }
    tooltip = { show: true, x, y, title, text, nodeId: opts.nodeId || "", sourceNodeId: opts.sourceNodeId || "", targetNodeId: opts.targetNodeId || "" };
  }

  function scheduleHideTooltip() {
    if (tooltipHideTimer) {
      clearTimeout(tooltipHideTimer);
    }
    tooltipHideTimer = setTimeout(() => {
      tooltip = { ...tooltip, show: false };
      tooltipHideTimer = null;
    }, TOOLTIP_HIDE_DELAY);
  }

  function cancelHideTooltip() {
    if (tooltipHideTimer) {
      clearTimeout(tooltipHideTimer);
      tooltipHideTimer = null;
    }
  }

  function setupTooltips() {
    if (!mermaidContainer || !$agentGraph) return;

    const knownNodeIds = new Set(Object.keys($agentGraph.nodes));

    // Setup node tooltips
    const nodes = mermaidContainer.querySelectorAll(".node");
    nodes.forEach((node) => {
      // Mermaid creates IDs like "flowchart-nodeId-123"
      // Split by "-" and find exact match for a known node ID
      const elementId = node.id || "";
      const segments = elementId.split("-");
      let matchedId: string | null = null;

      for (const segment of segments) {
        if (knownNodeIds.has(segment)) {
          matchedId = segment;
          break;
        }
      }

      // Fallback: check if element ID contains a known node ID as exact segment
      // (handles IDs with underscores that might span multiple dash-segments)
      if (!matchedId) {
        for (const knownId of knownNodeIds) {
          // Check for exact match with dash boundaries
          if (
            elementId === knownId ||
            elementId.startsWith(knownId + "-") ||
            elementId.endsWith("-" + knownId) ||
            elementId.includes("-" + knownId + "-")
          ) {
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
        showTooltip(
          rect.left + rect.width / 2,
          rect.top - 8,
          matchedId,
          nodeData.state_prompt,
          { nodeId: matchedId }
        );
      });
      node.addEventListener("mouseleave", () => {
        scheduleHideTooltip();
      });
      node.addEventListener("mousedown", (e) => {
        e.stopPropagation();
      });
      node.addEventListener("click", () => {
        tooltip = { ...tooltip, show: false };
        nodePromptModal?.open(matchedId, nodeData.state_prompt);
      });
    });

    // Setup edge label tooltips
    const edgeLabels = mermaidContainer.querySelectorAll(".edgeLabel");
    edgeLabels.forEach((label) => {
      const labelText = label.textContent?.trim() || "";
      if (!labelText) return;

      // Find the full transition condition and source/target node by matching truncated text
      let fullCondition = labelText;
      let sourceNodeId = "";
      let targetNodeId = "";
      for (const [nodeId, node] of Object.entries($agentGraph?.nodes || {})) {
        for (const transition of node.transitions) {
          const condValue = transition.condition.value;
          if (condValue.startsWith(labelText.replace("...", "")) ||
              labelText.replace("...", "") === condValue.slice(0, labelText.length - 3)) {
            fullCondition = condValue;
            sourceNodeId = nodeId;
            targetNodeId = transition.target_node_id;
            break;
          }
        }
        if (targetNodeId) break;
      }

      label.addEventListener("mouseenter", (e) => {
        const rect = (e.target as Element).getBoundingClientRect();
        const title = targetNodeId ? `${sourceNodeId} → ${targetNodeId}` : "Transition";
        showTooltip(
          rect.left + rect.width / 2,
          rect.top - 8,
          title,
          fullCondition,
          { sourceNodeId, targetNodeId }
        );
      });
      label.addEventListener("mouseleave", () => {
        scheduleHideTooltip();
      });
      label.addEventListener("mousedown", (e) => {
        e.stopPropagation();
      });
      label.addEventListener("click", () => {
        if (sourceNodeId && targetNodeId) {
          tooltip = { ...tooltip, show: false };
          transitionModal?.open(sourceNodeId, targetNodeId, fullCondition);
        }
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
    panX = 0;
    panY = 0;
  }

  function handleWheel(e: WheelEvent) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.04 : 0.04;
    const newZoom = Math.max(0.25, Math.min(3, zoomLevel + delta));

    // Zoom towards cursor position
    if (mermaidContainer) {
      const rect = mermaidContainer.getBoundingClientRect();
      const cursorX = e.clientX - rect.left;
      const cursorY = e.clientY - rect.top;

      // Adjust pan to zoom towards cursor
      const zoomRatio = newZoom / zoomLevel;
      panX = cursorX - (cursorX - panX) * zoomRatio;
      panY = cursorY - (cursorY - panY) * zoomRatio;
    }

    zoomLevel = newZoom;
  }

  function handleMouseDown(e: MouseEvent) {
    if (e.button !== 0) return; // Only left click
    isPanning = true;
    panStart = { x: e.clientX, y: e.clientY, panX, panY };
    e.preventDefault();
  }

  function handleMouseMove(e: MouseEvent) {
    if (!isPanning) return;
    panX = panStart.panX + (e.clientX - panStart.x);
    panY = panStart.panY + (e.clientY - panStart.y);
  }

  function handleMouseUp() {
    isPanning = false;
  }

  function getTouchDistance(touches: TouchList): number {
    return Math.hypot(
      touches[1].clientX - touches[0].clientX,
      touches[1].clientY - touches[0].clientY
    );
  }

  function getTouchCenter(touches: TouchList): { x: number; y: number } {
    return {
      x: (touches[0].clientX + touches[1].clientX) / 2,
      y: (touches[0].clientY + touches[1].clientY) / 2,
    };
  }

  function handleTouchStart(e: TouchEvent) {
    if (e.touches.length === 2) {
      e.preventDefault();
      const distance = getTouchDistance(e.touches);
      const center = getTouchCenter(e.touches);
      touchState = {
        distance,
        centerX: center.x,
        centerY: center.y,
        initialZoom: zoomLevel,
        initialPanX: panX,
        initialPanY: panY,
      };
    } else if (e.touches.length === 1) {
      isPanning = true;
      panStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, panX, panY };
    }
  }

  function handleTouchMove(e: TouchEvent) {
    if (e.touches.length === 2) {
      e.preventDefault();
      const distance = getTouchDistance(e.touches);
      const center = getTouchCenter(e.touches);

      // Calculate zoom
      const scale = distance / touchState.distance;
      const newZoom = Math.max(0.25, Math.min(3, touchState.initialZoom * scale));

      // Adjust pan to zoom towards pinch center
      if (mermaidContainer) {
        const rect = mermaidContainer.getBoundingClientRect();
        const centerX = center.x - rect.left;
        const centerY = center.y - rect.top;

        const zoomRatio = newZoom / touchState.initialZoom;
        panX = centerX - (centerX - touchState.initialPanX) * zoomRatio;
        panY = centerY - (centerY - touchState.initialPanY) * zoomRatio;
      }

      zoomLevel = newZoom;
    } else if (e.touches.length === 1 && isPanning) {
      panX = panStart.panX + (e.touches[0].clientX - panStart.x);
      panY = panStart.panY + (e.touches[0].clientY - panStart.y);
    }
  }

  function handleTouchEnd() {
    isPanning = false;
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

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape" && transitionModal?.isOpen()) {
      transitionModal.close();
      return;
    }
    if (e.key === "Escape" && nodePromptModal?.isOpen()) {
      nodePromptModal.close();
      return;
    }
    if (e.key === "Escape" && showExportModal) {
      showExportModal = false;
    }
    if (e.key === "Escape" && editingName) {
      editingName = false;
    }
    if (e.key === "Escape" && editingModel) {
      editingModel = false;
    }
    if (e.key === "Escape" && editingGeneralPrompt) {
      editingGeneralPrompt = false;
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
      await api.updateAgent($currentAgentId, { name: editedName.trim() });
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

  function startEditingModel() {
    editedModel = $agentGraph?.default_model || "";
    editingModel = true;
    requestAnimationFrame(() => {
      modelInput?.focus();
      modelInput?.select();
    });
  }

  async function saveModel() {
    if (!$currentAgentId) {
      editingModel = false;
      return;
    }
    const newModel = editedModel.trim() || undefined;
    const currentModel = $agentGraph?.default_model || undefined;
    if (newModel === currentModel) {
      editingModel = false;
      return;
    }
    savingModel = true;
    try {
      // Send the updated graph to handle both file-based and stored agents
      const updatedGraph = $agentGraph ? { ...$agentGraph, default_model: newModel || null } : null;
      await api.updateAgent($currentAgentId, {
        default_model: newModel,
        graph_json: updatedGraph ? JSON.stringify(updatedGraph) : undefined,
      });
      await loadAgents();
      if (updatedGraph) {
        agentGraph.set(updatedGraph);
      }
      editingModel = false;
      modelSaved = true;
      setTimeout(() => { modelSaved = false; }, 2000);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    savingModel = false;
  }

  function handleModelKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") {
      saveModel();
    }
  }

  async function refreshFromFile() {
    if (!$currentAgentId) return;
    refreshing = true;
    try {
      await refreshAgent($currentAgentId);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    refreshing = false;
  }

  async function syncToSource() {
    if (!$currentAgentId || !$agentGraph || !syncStatus?.can_sync) return;
    syncing = true;
    syncError = "";
    syncSuccess = false;
    try {
      await api.syncToPlatform($currentAgentId, $agentGraph);
      syncSuccess = true;
      setTimeout(() => { syncSuccess = false; }, 3000);
    } catch (e) {
      syncError = e instanceof Error ? e.message : String(e);
    }
    syncing = false;
  }

  function startEditingGeneralPrompt() {
    editedGeneralPrompt = String($agentGraph?.source_metadata?.general_prompt ?? "");
    editingGeneralPrompt = true;
    requestAnimationFrame(() => {
      generalPromptTextarea?.focus();
    });
  }

  async function saveGeneralPrompt() {
    if (!$currentAgentId) {
      editingGeneralPrompt = false;
      return;
    }
    const current = String($agentGraph?.source_metadata?.general_prompt ?? "");
    if (editedGeneralPrompt === current) {
      editingGeneralPrompt = false;
      return;
    }
    savingGeneralPrompt = true;
    try {
      const result = await api.updatePrompt($currentAgentId, null, editedGeneralPrompt);
      agentGraph.set(result);
      editingGeneralPrompt = false;
      generalPromptSaved = true;
      setTimeout(() => { generalPromptSaved = false; }, 2000);
      requestAnimationFrame(() => setupTooltips());
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    savingGeneralPrompt = false;
  }

  function handleChildError(msg: string) {
    error = msg;
  }

  function handleTooltipsChanged() {
    requestAnimationFrame(() => setupTooltips());
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
        <span class="label">LLM:</span>
        <span class="model-value">
          {#if editingModel}
            <input
              type="text"
              class="model-input"
              bind:value={editedModel}
              bind:this={modelInput}
              onblur={saveModel}
              onkeydown={handleModelKeydown}
              disabled={savingModel}
              placeholder="e.g. openai/gpt-4o"
            />
          {:else}
            <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
            <span class="editable-model" onclick={startEditingModel} title="Click to edit">
              {$agentGraph.default_model || "Not set"}
            </span>
          {/if}
          {#if savingModel}
            <span class="model-save-indicator">Saving...</span>
          {:else if modelSaved}
            <span class="model-save-indicator saved">Saved</span>
          {/if}
        </span>
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
          <span class="linked-file">
            <span class="mono">{$currentAgent.source_path}</span>
            <button
              class="refresh-btn"
              onclick={refreshFromFile}
              disabled={refreshing}
              title="Reload agent from file"
            >
              <span class="refresh-icon" class:spinning={refreshing}>↻</span>
            </button>
          </span>
        </div>
      {/if}
    </section>

    <section class="general-prompt">
      <div class="prompt-header">
        <h3>General Prompt</h3>
        {#if savingGeneralPrompt}
          <span class="save-indicator">Saving...</span>
        {:else if generalPromptSaved}
          <span class="save-indicator saved">Saved</span>
        {/if}
      </div>
      {#if editingGeneralPrompt}
        <textarea
          class="prompt-textarea"
          bind:value={editedGeneralPrompt}
          bind:this={generalPromptTextarea}
          onblur={saveGeneralPrompt}
          disabled={savingGeneralPrompt}
          rows="10"
        ></textarea>
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
        <pre
          class="prompt-text clickable"
          onclick={startEditingGeneralPrompt}
          title="Click to edit"
        >{$agentGraph.source_metadata?.general_prompt || "(No general prompt — click to add)"}</pre>
      {/if}
    </section>

    {#if $currentAgentId}
      <SnippetManager agentId={$currentAgentId} bind:snippets onerror={handleChildError} />
    {/if}

    <div class="actions">
      <ChatView />
      <CallView />
      <button
        class="btn-primary"
        onclick={() => (showExportModal = true)}
      >
        Export Agent...
      </button>
      {#if syncStatus}
        {#if syncStatus.can_sync}
          <button
            class="sync-btn"
            onclick={syncToSource}
            disabled={syncing}
          >
            {#if syncing}
              Syncing...
            {:else if syncSuccess}
              Synced!
            {:else}
              Sync to {getPlatformDisplayName(syncStatus.platform || "")}
            {/if}
          </button>
        {:else if syncStatus.platform}
          <span class="sync-unavailable" title={syncStatus.reason || ""}>
            Sync unavailable
            {#if syncStatus.needs_configuration}
              (configure {getPlatformDisplayName(syncStatus.platform)} first)
            {/if}
          </span>
        {/if}
      {/if}
    </div>
    {#if error}
      <p class="error-message">{error}</p>
    {/if}
    {#if syncError}
      <p class="error-message">{syncError}</p>
    {/if}

    <ExportModal bind:show={showExportModal} {snippets} onerror={handleChildError} />

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
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        class="mermaid-container"
        class:panning={isPanning}
        bind:this={mermaidContainer}
        onwheel={handleWheel}
        onmousedown={handleMouseDown}
        onmousemove={handleMouseMove}
        onmouseup={handleMouseUp}
        onmouseleave={handleMouseUp}
        ontouchstart={handleTouchStart}
        ontouchmove={handleTouchMove}
        ontouchend={handleTouchEnd}
      >
        <div class="mermaid-content" style="transform: translate({panX}px, {panY}px) scale({zoomLevel}); transform-origin: 0 0;">
          {@html mermaidSvg}
        </div>
      </div>
    </section>

    {#if $currentAgentId}
      <MetadataEditor agentId={$currentAgentId} onerror={handleChildError} />
    {/if}

    {#if tooltip.show}
      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
      <div
        class="node-tooltip"
        class:clickable={tooltip.nodeId !== "" || (tooltip.sourceNodeId !== "" && tooltip.targetNodeId !== "")}
        style="left: {tooltip.x}px; top: {tooltip.y}px;"
        onmouseenter={cancelHideTooltip}
        onmouseleave={scheduleHideTooltip}
        onclick={() => {
          const nid = tooltip.nodeId;
          const src = tooltip.sourceNodeId;
          const tgt = tooltip.targetNodeId;
          const text = tooltip.text;
          tooltip = { ...tooltip, show: false };
          if (nid) {
            const nodeData = $agentGraph?.nodes[nid];
            if (nodeData) {
              nodePromptModal?.open(nid, nodeData.state_prompt);
            }
          } else if (src && tgt) {
            transitionModal?.open(src, tgt, text);
          }
        }}
      >
        {#if tooltip.title}
          <div class="tooltip-title">{tooltip.title}</div>
        {/if}
        <div class="tooltip-text">{tooltip.text}</div>
      </div>
    {/if}

    {#if $currentAgentId}
      <NodePromptModal
        bind:this={nodePromptModal}
        agentId={$currentAgentId}
        onerror={handleChildError}
        ontooltipschanged={handleTooltipsChanged}
      />
      <TransitionModal
        bind:this={transitionModal}
        agentId={$currentAgentId}
        onerror={handleChildError}
        ontooltipschanged={handleTooltipsChanged}
      />
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

  .linked-file {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .refresh-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.15rem 0.35rem;
    font-size: 0.85rem;
    line-height: 1;
    transition: color 0.15s, border-color 0.15s;
  }

  .refresh-btn:hover:not(:disabled) {
    color: var(--text-primary);
    border-color: var(--text-secondary);
  }

  .refresh-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .refresh-icon.spinning {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .general-prompt {
    margin-bottom: 1.5rem;
    padding: var(--space-4);
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
  }

  .prompt-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .prompt-text {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: var(--text-sm);
    color: var(--text-secondary);
    line-height: 1.5;
    max-height: 300px;
    overflow-y: auto;
  }

  .prompt-text.clickable {
    cursor: pointer;
    padding: 0.5rem;
    margin: -0.5rem;
    border-radius: var(--radius-sm);
    transition: background 0.15s;
  }

  .prompt-text.clickable:hover {
    background: var(--bg-hover);
  }

  .prompt-textarea {
    width: 100%;
    min-height: 120px;
    padding: 0.5rem;
    font-family: monospace;
    font-size: var(--text-sm);
    line-height: 1.5;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--accent-color, #6366f1);
    border-radius: var(--radius-sm);
    resize: vertical;
    outline: none;
  }

  .prompt-textarea:disabled {
    opacity: 0.6;
  }

  .model-value {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .editable-model {
    cursor: pointer;
    padding: 0.15rem 0.4rem;
    margin: -0.15rem -0.4rem;
    border-radius: 4px;
    transition: background 0.15s;
    font-family: monospace;
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .editable-model:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .model-input {
    font-family: monospace;
    font-size: 0.85rem;
    padding: 0.15rem 0.4rem;
    border: 1px solid var(--accent-color, #6366f1);
    border-radius: 4px;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    outline: none;
    min-width: 180px;
  }

  .model-save-indicator {
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .model-save-indicator.saved {
    color: #22c55e;
  }

  .actions {
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .sync-btn {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
    transition: background 0.15s, border-color 0.15s;
  }

  .sync-btn:hover:not(:disabled) {
    background: var(--bg-hover);
    border-color: var(--accent);
  }

  .sync-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .sync-unavailable {
    font-size: 0.85rem;
    color: var(--text-secondary);
    cursor: help;
    padding: 0.5rem 0;
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
    overflow: hidden;
    height: 100vh;
    min-height: 400px;
    cursor: grab;
    user-select: none;
    touch-action: none;
  }

  .mermaid-container.panning {
    cursor: grabbing;
  }

  .mermaid-content {
    display: inline-block;
    min-width: 100%;
    height: 100%;
  }

  .mermaid-content :global(svg) {
    display: block;
    min-height: 100%;
    width: auto;
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

  .node-tooltip.clickable {
    cursor: pointer;
  }

  .node-tooltip.clickable:hover {
    border-color: var(--accent-color, #6366f1);
  }


  .snippets-section {
    margin-bottom: 1.5rem;
    padding: var(--space-4);
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
  }

  .snippets-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .snippets-actions {
    display: flex;
    gap: 0.5rem;
  }

  .btn-sm {
    padding: 0.3rem 0.6rem;
    font-size: 0.8rem;
  }

  .btn-xs {
    padding: 0.2rem 0.5rem;
    font-size: 0.75rem;
  }

  .danger-text {
    color: var(--danger-text);
  }

  .snippet-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .snippet-item {
    padding: 0.5rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
  }

  .snippet-name-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
  }

  .snippet-ref {
    font-family: monospace;
    font-size: 0.8rem;
    color: var(--accent-color, #6366f1);
  }

  .snippet-btns {
    display: flex;
    gap: 0.25rem;
  }

  .snippet-preview {
    margin: 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
    white-space: pre-wrap;
    word-wrap: break-word;
    max-height: 80px;
    overflow-y: auto;
  }

  .snippet-textarea {
    width: 100%;
    padding: 0.4rem;
    font-family: monospace;
    font-size: 0.8rem;
    line-height: 1.4;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--accent-color, #6366f1);
    border-radius: var(--radius-sm);
    resize: vertical;
    outline: none;
  }

  .snippet-edit-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.25rem;
    margin-top: 0.25rem;
  }

  .snippet-add-form {
    margin-top: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .snippet-name-input {
    padding: 0.3rem 0.5rem;
    font-family: monospace;
    font-size: 0.8rem;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--bg-tertiary);
    color: var(--text-primary);
    outline: none;
  }

  .snippet-empty {
    font-size: 0.85rem;
    color: var(--text-secondary);
    font-style: italic;
    margin: 0;
  }

  .dry-results {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
  }

  .dry-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .dry-header h4 {
    margin: 0;
    font-size: 0.9rem;
    color: var(--text-primary);
  }

  .dry-section h5 {
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin: 0.5rem 0 0.25rem;
  }

  .dry-match {
    padding: 0.5rem;
    margin-bottom: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--bg-secondary);
  }

  .dry-text {
    margin: 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
    white-space: pre-wrap;
    word-wrap: break-word;
    max-height: 80px;
    overflow-y: auto;
  }

  .dry-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 0.25rem;
  }

  .dry-locations {
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .dry-similarity {
    font-size: 0.75rem;
    color: var(--accent-color, #6366f1);
    font-weight: 500;
    margin-bottom: 0.25rem;
  }

  .dry-empty {
    font-size: 0.85rem;
    color: var(--text-secondary);
    font-style: italic;
    margin: 0;
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

  .tabs {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border-color);
  }

  .tab {
    flex: 1;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: var(--space-3) var(--space-4);
    margin-bottom: -1px;
    cursor: pointer;
    color: var(--text-secondary);
    font-size: var(--text-sm);
    transition: color 80ms ease-out, border-color 80ms ease-out;
  }

  .tab:hover {
    color: var(--text-primary);
    background: transparent;
  }

  .tab.active {
    color: var(--text-primary);
    font-weight: 600;
    border-bottom-color: var(--tab-highlight);
    background: transparent;
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
    max-height: calc(80vh - 100px);
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 0.5rem;
    margin-top: var(--space-3);
  }

  .node-prompt-modal {
    min-width: 500px;
    max-width: 700px;
  }

  .node-prompt-modal .prompt-textarea {
    min-height: 250px;
  }

  .tab-panels {
    display: grid;
  }

  .tab-panel {
    grid-area: 1 / 1;
    visibility: hidden;
  }

  .tab-panel.active {
    visibility: visible;
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

  .platform-export-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .platform-export-row {
    margin-bottom: 0;
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
    min-width: 60px;
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

  .platform-action-btn {
    margin-left: auto;
    min-width: 140px;
    text-align: center;
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

    .platform-action-btn {
      margin-left: 0;
      width: 100%;
    }
  }

  .metadata-section {
    margin-bottom: 1.5rem;
    padding: var(--space-4);
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
  }

  .metadata-header {
    cursor: pointer;
    user-select: none;
  }

  .metadata-header h3 {
    margin: 0;
  }

  .metadata-fields {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-top: 0.75rem;
  }

  .metadata-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .metadata-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: var(--text-sm);
    color: var(--text-secondary);
  }

  .metadata-label code {
    font-size: var(--text-sm);
    color: var(--text-primary);
  }

  .metadata-value.readonly {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: var(--text-sm);
    color: var(--text-secondary);
    line-height: 1.5;
    max-height: 200px;
    overflow-y: auto;
    background: var(--bg-tertiary);
    padding: 0.5rem;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
  }

  .metadata-value.editable {
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    color: var(--text-secondary);
    transition: background 0.15s;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .metadata-value.editable:hover {
    background: var(--bg-hover);
  }

  .metadata-textarea {
    width: 100%;
    padding: 0.5rem;
    font-family: monospace;
    font-size: var(--text-sm);
    line-height: 1.5;
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--accent-color, #6366f1);
    border-radius: var(--radius-sm);
    resize: vertical;
    box-sizing: border-box;
  }
</style>
