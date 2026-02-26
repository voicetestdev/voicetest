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
