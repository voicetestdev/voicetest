<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import {
    agentGraph,
    currentAgent,
  } from "../lib/stores";
  import type { ExporterInfo, Platform, PlatformInfo, PlatformStatus } from "../lib/types";

  interface Props {
    show: boolean;
    snippets?: Record<string, string>;
    onerror?: (msg: string) => void;
  }

  let { show = $bindable(false), snippets = {}, onerror }: Props = $props();

  let exporters = $state<ExporterInfo[]>([]);
  let exporting = $state(false);
  let exportTab = $state<"file" | "platform">("file");
  let platforms = $state<PlatformInfo[]>([]);
  let platformStatus = $state<Record<string, PlatformStatus>>({});
  let apiKeyInput = $state("");
  let configuringPlatform = $state<string | null>(null);
  let exportingToPlatform = $state<string | null>(null);
  let exportSuccess = $state<{ platform: string; id: string; name: string } | null>(null);
  let error = $state("");

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

  onMount(() => {
    api.listExporters().then((list) => {
      exporters = list;
    });
  });

  $effect(() => {
    if (show) {
      api.listPlatforms().then((list) => {
        platforms = list;
        platformStatus = Object.fromEntries(
          list.map((p) => [p.name, { platform: p.name, configured: p.configured }])
        );
      }).catch(() => {});
      exportSuccess = null;
      error = "";
    }
  });

  function reportError(msg: string) {
    error = msg;
    onerror?.(msg);
  }

  function getExportFilename(exp: ExporterInfo): string {
    const agentName = $currentAgent?.name || "agent";
    const safeName = agentName.replace(/[^a-zA-Z0-9_-]/g, "_");
    const suffix = exp.id.replace(/-/g, "_");
    return `${safeName}_${suffix}.${exp.ext}`;
  }

  function getExportFilenameForFormat(format: string, ext: string): string {
    const agentName = $currentAgent?.name || "agent";
    const safeName = agentName.replace(/[^a-zA-Z0-9_-]/g, "_");
    const suffix = format.replace(/-/g, "_");
    return `${safeName}_${suffix}.${ext}`;
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
      show = false;
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    exporting = false;
  }

  async function exportToPlatform(platform: Platform) {
    if (!$agentGraph) return;
    exportingToPlatform = platform;
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
      reportError(e instanceof Error ? e.message : String(e));
    }
    exportingToPlatform = null;
  }

  async function configureAndExport(platform: Platform) {
    if (!apiKeyInput.trim()) {
      reportError("Please enter an API key");
      return;
    }
    configuringPlatform = platform;
    error = "";
    try {
      const status = await api.configurePlatform(platform, apiKeyInput);
      platformStatus = { ...platformStatus, [platform]: status };
      apiKeyInput = "";
      await exportToPlatform(platform);
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    configuringPlatform = null;
  }

  async function exportRawVtJson() {
    if (!$agentGraph) return;
    exporting = true;
    error = "";
    try {
      const result = await api.exportAgent($agentGraph, "voicetest");
      const blob = new Blob([result.content], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = getExportFilenameForFormat("voicetest", "vt.json");
      a.click();
      URL.revokeObjectURL(url);
      show = false;
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    exporting = false;
  }

  async function exportExpanded(exp: ExporterInfo) {
    if (!$agentGraph) return;
    exporting = true;
    error = "";
    try {
      const result = await api.exportAgent($agentGraph, exp.id, true);
      const blob = new Blob([result.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = getExportFilename(exp);
      a.click();
      URL.revokeObjectURL(url);
      show = false;
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    exporting = false;
  }

  function closeModal(e: MouseEvent) {
    if ((e.target as HTMLElement).classList.contains("modal-backdrop")) {
      show = false;
    }
  }
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="modal-backdrop" onclick={closeModal}>
    <div class="modal">
      <div class="modal-header">
        <h3>Export Agent</h3>
        <button class="close-btn" onclick={() => (show = false)}>&times;</button>
      </div>
      {#if exportSuccess}
        <div class="modal-body">
          <div class="export-success">
            <div class="success-icon">&#10003;</div>
            <p>Agent created in {getPlatformDisplayName(exportSuccess.platform)}!</p>
            <p class="success-details">
              <strong>{exportSuccess.name}</strong><br />
              <span class="mono">{exportSuccess.id}</span>
            </p>
            <button onclick={() => (exportSuccess = null)}>Export Another</button>
          </div>
        </div>
      {:else}
        <div class="tabs">
          <button
            class="tab"
            class:active={exportTab === "file"}
            onclick={() => (exportTab = "file")}
          >
            Download File
          </button>
          <button
            class="tab"
            class:active={exportTab === "platform"}
            onclick={() => (exportTab = "platform")}
          >
            To Platform
          </button>
        </div>
        <div class="modal-body">
          <div class="tab-panels">
            <div class="tab-panel" class:active={exportTab === "file"}>
              <div class="export-options">
                {#if Object.keys(snippets).length > 0}
                  <button
                    class="export-option"
                    onclick={() => exportRawVtJson()}
                    disabled={exporting}
                  >
                    <span class="export-name">Raw (.vt.json)</span>
                    <span class="export-desc">Preserves snippet references for sharing with teammates</span>
                    <span class="export-ext">.vt.json</span>
                  </button>
                {/if}
                {#each exporters as exp}
                  {#if Object.keys(snippets).length > 0 && exp.id !== "voicetest"}
                    <button
                      class="export-option"
                      onclick={() => exportExpanded(exp)}
                      disabled={exporting}
                    >
                      <span class="export-name">{exp.name} (Expanded)</span>
                      <span class="export-desc">{exp.description} &mdash; snippets resolved</span>
                      <span class="export-ext">.{exp.ext}</span>
                    </button>
                  {:else}
                    <button
                      class="export-option"
                      onclick={() => exportTo(exp)}
                      disabled={exporting}
                    >
                      <span class="export-name">{exp.name}</span>
                      <span class="export-desc">{exp.description}</span>
                      <span class="export-ext">.{exp.ext}</span>
                    </button>
                  {/if}
                {/each}
              </div>
            </div>
            <div class="tab-panel" class:active={exportTab === "platform"}>
              <div class="platform-export-list">
                {#each platforms as platform}
                  {@const status = platformStatus[platform.name]}
                  {@const displayName = getPlatformDisplayName(platform.name)}
                  {@const isExporting = exportingToPlatform === platform.name}
                  {@const isConfiguring = configuringPlatform === platform.name}
                  {@const isBusy = exportingToPlatform !== null || configuringPlatform !== null}
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
                          class="platform-action-btn"
                          onclick={() => configureAndExport(platform.name)}
                          disabled={isBusy || !apiKeyInput.trim()}
                        >
                          {isConfiguring || isExporting ? "..." : "Connect & Export"}
                        </button>
                      </div>
                    {:else}
                      <div class="platform-configured">
                        <span class="platform-label">{displayName}</span>
                        <span class="connected-badge-small">Connected</span>
                        <button
                          class="platform-action-btn"
                          onclick={() => exportToPlatform(platform.name)}
                          disabled={isBusy}
                        >
                          {isExporting ? "Creating..." : `Create in ${displayName}`}
                        </button>
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          </div>
          {#if error}
            <p class="modal-error">{error}</p>
          {/if}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .modal {
    min-width: 400px;
    max-width: 550px;
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
</style>
