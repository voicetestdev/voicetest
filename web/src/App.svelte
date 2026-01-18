<script lang="ts">
  import { onMount } from "svelte";
  import {
    currentView,
    initStores,
    agents,
    currentAgentId,
    expandedAgents,
    selectAgent,
    selectRun,
    toggleAgentExpanded,
    testCaseRecords,
    runHistory,
    expandedRuns,
    currentRunId,
  } from "./lib/stores";
  import type { RunRecord } from "./lib/types";
  import AgentView from "./components/AgentView.svelte";
  import TestsView from "./components/TestsView.svelte";
  import RunsView from "./components/RunsView.svelte";
  import SettingsView from "./components/SettingsView.svelte";
  import ImportView from "./components/ImportView.svelte";

  let initialized = $state(false);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      await initStores();
      initialized = true;
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to initialize";
    }
  });

  function handleAgentClick(agentId: string) {
    if ($currentAgentId === agentId) {
      toggleAgentExpanded(agentId);
    } else {
      selectAgent(agentId, "config");
    }
  }

  function handleNavClick(agentId: string, view: "config" | "tests" | "runs") {
    // selectAgent will automatically load the first run when view is "runs"
    selectAgent(agentId, view);
  }

  function toggleRuns(e: Event) {
    e.stopPropagation();
    expandedRuns.update((v) => !v);
  }

  function selectRunFromSidebar(agentId: string, run: RunRecord) {
    selectRun(agentId, run.id);
  }

  function formatRelativeTime(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }
</script>

<div class="app">
  <nav>
    <h1>voicetest</h1>

    <div class="nav-section">
      <ul class="agent-tree">
        {#each $agents as agent}
          {@const isExpanded = $expandedAgents.has(agent.id)}
          {@const isSelected = $currentAgentId === agent.id}
          {@const testCount = isSelected ? $testCaseRecords.length : 0}
          {@const runCount = isSelected ? $runHistory.length : 0}
          <li class="agent-item">
            <button
              class="agent-toggle"
              class:expanded={isExpanded}
              class:selected={isSelected}
              onclick={() => handleAgentClick(agent.id)}
            >
              <span class="chevron">{isExpanded ? "▼" : "▶"}</span>
              <span class="agent-name">{agent.name}</span>
            </button>

            {#if isExpanded}
              <ul class="agent-subnav">
                <li>
                  <button
                    class:active={isSelected && $currentView === "config"}
                    onclick={() => handleNavClick(agent.id, "config")}
                  >
                    Config
                  </button>
                </li>
                <li>
                  <button
                    class:active={isSelected && $currentView === "tests"}
                    onclick={() => handleNavClick(agent.id, "tests")}
                  >
                    Tests {#if testCount > 0}<span class="count">({testCount})</span>{/if}
                  </button>
                </li>
                <li>
                  <button
                    class="runs-btn"
                    class:active={isSelected && $currentView === "runs"}
                    onclick={() => handleNavClick(agent.id, "runs")}
                  >
                    {#if runCount > 0}
                      <span
                        class="runs-chevron"
                        role="button"
                        tabindex="0"
                        onclick={toggleRuns}
                        onkeydown={(e) => e.key === "Enter" && toggleRuns(e)}
                      >{$expandedRuns ? "▼" : "▶"}</span>
                    {/if}
                    Runs {#if runCount > 0}<span class="count">({runCount})</span>{/if}
                  </button>
                  {#if isSelected && $expandedRuns && runCount > 0}
                    <ul class="run-history-list">
                      {#each $runHistory.slice(0, 10) as run}
                        <li>
                          <button
                            class:active={$currentView === "runs" && $currentRunId === run.id}
                            onclick={() => selectRunFromSidebar(agent.id, run)}
                          >
                            {formatRelativeTime(run.started_at)}
                            {#if !run.completed_at}
                              <span class="mini-spinner"></span>
                            {/if}
                          </button>
                        </li>
                      {/each}
                    </ul>
                  {/if}
                </li>
              </ul>
            {/if}
          </li>
        {/each}
      </ul>
    </div>

    <div class="nav-footer">
      <button
        class="import-btn"
        class:active={$currentView === "import"}
        onclick={() => currentView.set("import")}
      >
        + Import Agent
      </button>
      <button
        class:active={$currentView === "settings"}
        onclick={() => currentView.set("settings")}
      >
        Settings
      </button>
    </div>
  </nav>

  <main>
    {#if error}
      <div class="error-panel">
        <p>Error: {error}</p>
        <button onclick={() => window.location.reload()}>Retry</button>
      </div>
    {:else if !initialized}
      <div class="loading">Loading...</div>
    {:else if $currentView === "import"}
      <ImportView />
    {:else if $currentView === "config"}
      <AgentView />
    {:else if $currentView === "tests"}
      <TestsView />
    {:else if $currentView === "runs"}
      <RunsView />
    {:else if $currentView === "settings"}
      <SettingsView />
    {/if}
  </main>
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, -apple-system, sans-serif;
    background: #1a1a2e;
    color: #e8e8e8;
  }

  :global(*) {
    box-sizing: border-box;
  }

  .app {
    display: flex;
    height: 100vh;
  }

  nav {
    width: 220px;
    background: #16213e;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
  }

  nav h1 {
    font-size: 1.25rem;
    margin: 0;
    color: #3b82f6;
  }

  .nav-section {
    flex: 1;
    overflow-y: auto;
  }

  .agent-tree {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .agent-item {
    display: flex;
    flex-direction: column;
  }

  .agent-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    text-align: left;
    padding: 0.5rem 0.5rem;
    background: transparent;
    border: none;
    color: #e8e8e8;
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.9rem;
  }

  .agent-toggle:hover {
    background: #1a1a2e;
  }

  .agent-toggle.selected {
    background: #1f2937;
  }

  .chevron {
    font-size: 0.7rem;
    color: #6b7280;
    width: 1rem;
  }

  .agent-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .agent-subnav {
    list-style: none;
    padding: 0;
    margin: 0 0 0.5rem 1.1rem;
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .agent-subnav button {
    width: 100%;
    text-align: left;
    padding: 0.35rem 0.75rem 0.35rem 1.1rem;
    background: transparent;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.85rem;
  }

  .agent-subnav button:hover {
    background: #1a1a2e;
    color: #e8e8e8;
  }

  .agent-subnav button.active {
    background: #3b82f6;
    color: white;
  }

  .count {
    color: #6b7280;
    font-size: 0.8rem;
  }

  .agent-subnav button.active .count {
    color: rgba(255, 255, 255, 0.7);
  }

  .runs-btn {
    position: relative;
  }

  .runs-chevron {
    position: absolute;
    left: 0.2rem;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.6rem;
    color: #6b7280;
    padding: 0.2rem;
    cursor: pointer;
  }

  .runs-chevron:hover {
    color: #9ca3af;
  }

  .run-history-list {
    list-style: none;
    padding: 0;
    margin: 0.25rem 0 0 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .run-history-list button {
    width: 100%;
    text-align: left;
    padding: 0.25rem 0.5rem;
    background: transparent;
    border: none;
    color: #6b7280;
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .run-history-list button:hover {
    background: #1a1a2e;
    color: #9ca3af;
  }

  .run-history-list button.active {
    background: #3b82f6;
    color: white;
  }

  .mini-spinner {
    width: 10px;
    height: 10px;
    border: 1.5px solid #374151;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .nav-footer {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    border-top: 1px solid #374151;
    padding-top: 1rem;
  }

  .nav-footer button {
    width: 100%;
    text-align: left;
    padding: 0.5rem 0.75rem;
    background: transparent;
    border: none;
    color: #e8e8e8;
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.9rem;
  }

  .nav-footer button:hover {
    background: #1a1a2e;
  }

  .nav-footer button.active {
    background: #3b82f6;
    color: white;
  }

  .import-btn {
    color: #3b82f6 !important;
  }

  main {
    flex: 1;
    padding: 1.5rem;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #9ca3af;
  }

  .error-panel {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 1rem;
    color: #f87171;
  }

  :global(.pass) {
    color: #4ade80;
  }
  :global(.fail) {
    color: #f87171;
  }
  :global(.error) {
    color: #fbbf24;
  }

  :global(button) {
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.9rem;
  }

  :global(button:hover) {
    background: #2563eb;
  }

  :global(button:disabled) {
    background: #4b5563;
    cursor: not-allowed;
  }

  :global(textarea),
  :global(input[type="text"]) {
    background: #16213e;
    border: 1px solid #374151;
    color: #e8e8e8;
    padding: 0.5rem;
    border-radius: 4px;
    font-family: inherit;
    font-size: 0.9rem;
  }

  :global(textarea:focus),
  :global(input:focus) {
    outline: none;
    border-color: #3b82f6;
  }
</style>
