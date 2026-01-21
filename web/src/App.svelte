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
  import MetricsView from "./components/MetricsView.svelte";
  import RunsView from "./components/RunsView.svelte";
  import SettingsView from "./components/SettingsView.svelte";
  import ImportView from "./components/ImportView.svelte";

  let initialized = $state(false);
  let error = $state<string | null>(null);
  let mobileNavOpen = $state(false);
  let theme = $state<"light" | "dark">("dark");

  function initTheme() {
    const stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") {
      theme = stored;
    } else if (window.matchMedia("(prefers-color-scheme: light)").matches) {
      theme = "light";
    }
  }

  function toggleTheme() {
    theme = theme === "dark" ? "light" : "dark";
    localStorage.setItem("theme", theme);
  }

  $effect(() => {
    document.documentElement.dataset.theme = theme;
  });

  onMount(async () => {
    initTheme();
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

  function handleNavClick(agentId: string, view: "config" | "tests" | "metrics" | "runs") {
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
  <button class="mobile-menu-btn" onclick={() => mobileNavOpen = !mobileNavOpen}>
    {mobileNavOpen ? "✕" : "☰"}
  </button>

  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <nav class:open={mobileNavOpen} onclick={() => mobileNavOpen = false}>
    <a href="/" class="logo-link">
      <img src={theme === "dark" ? "/logo-dark.svg" : "/logo-light.svg"} alt="voicetest" class="logo" />
    </a>

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
                    class:active={isSelected && $currentView === "metrics"}
                    onclick={() => handleNavClick(agent.id, "metrics")}
                  >
                    Metrics
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
      <button class="theme-toggle" onclick={toggleTheme} title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
        <span class="toggle-track">
          <span class="toggle-thumb"></span>
        </span>
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
      <AgentView {theme} />
    {:else if $currentView === "tests"}
      <TestsView />
    {:else if $currentView === "metrics"}
      <MetricsView />
    {:else if $currentView === "runs"}
      <RunsView />
    {:else if $currentView === "settings"}
      <SettingsView />
    {/if}
  </main>
</div>

<style>
  :global(:root) {
    --bg-primary: #1a1a2e;
    --bg-secondary: #16213e;
    --bg-tertiary: #1f2937;
    --bg-hover: #374151;
    --bg-input: #16213e;
    --text-primary: #e8e8e8;
    --text-secondary: #9ca3af;
    --text-muted: #6b7280;
    --border-color: #374151;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --color-pass: #4ade80;
    --color-fail: #f87171;
    --color-error: #fbbf24;
    --status-pass-bg: #064e3b;
    --status-fail-bg: #7f1d1d;
    --status-error-bg: #78350f;
    --danger-bg: #7f1d1d;
    --danger-bg-hover: #991b1b;
    --danger-text: #fecaca;
  }

  :global([data-theme="light"]) {
    --bg-primary: #f9fafb;
    --bg-secondary: #ffffff;
    --bg-tertiary: #f3f4f6;
    --bg-hover: #e5e7eb;
    --bg-input: #ffffff;
    --text-primary: #111827;
    --text-secondary: #4b5563;
    --text-muted: #9ca3af;
    --border-color: #d1d5db;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --color-pass: #15803d;
    --color-fail: #dc2626;
    --color-error: #d97706;
    --status-pass-bg: #dcfce7;
    --status-fail-bg: #fee2e2;
    --status-error-bg: #fef3c7;
    --danger-bg: #dc2626;
    --danger-bg-hover: #b91c1c;
    --danger-text: #ffffff;
  }

  :global(body) {
    margin: 0;
    font-family: system-ui, -apple-system, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
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
    background: var(--bg-secondary);
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
  }

  .logo-link {
    display: block;
    text-decoration: none;
  }

  .logo {
    height: 28px;
    width: auto;
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
    color: var(--text-primary);
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.9rem;
  }

  .agent-toggle:hover {
    background: var(--bg-primary);
  }

  .agent-toggle.selected {
    background: var(--bg-tertiary);
  }

  .chevron {
    font-size: 0.7rem;
    color: var(--text-muted);
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
    color: var(--text-secondary);
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.85rem;
  }

  .agent-subnav button:hover {
    background: var(--bg-primary);
    color: var(--text-primary);
  }

  .agent-subnav button.active {
    background: var(--accent);
    color: white;
  }

  .count {
    color: var(--text-muted);
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
    color: var(--text-muted);
    padding: 0.2rem;
    cursor: pointer;
  }

  .runs-chevron:hover {
    color: var(--text-secondary);
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
    color: var(--text-muted);
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .run-history-list button:hover {
    background: var(--bg-primary);
    color: var(--text-secondary);
  }

  .run-history-list button.active {
    background: var(--accent);
    color: white;
  }

  .mini-spinner {
    width: 10px;
    height: 10px;
    border: 1.5px solid var(--border-color);
    border-top-color: var(--accent);
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
    border-top: 1px solid var(--border-color);
    padding-top: 1rem;
  }

  .nav-footer button {
    width: 100%;
    text-align: left;
    padding: 0.5rem 0.75rem;
    background: transparent;
    border: none;
    color: var(--text-primary);
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.9rem;
  }

  .nav-footer button:hover {
    background: var(--bg-primary);
  }

  .nav-footer button.active {
    background: var(--accent);
    color: white;
  }

  .import-btn {
    color: var(--accent) !important;
  }

  .import-btn.active {
    color: white !important;
  }

  .theme-toggle {
    display: flex !important;
    align-items: center;
    justify-content: center;
    padding: 0.5rem 0.75rem !important;
    background: transparent !important;
  }

  .theme-toggle:hover {
    background: var(--bg-primary) !important;
  }

  .toggle-track {
    width: 36px;
    height: 20px;
    background: var(--bg-hover);
    border-radius: 10px;
    position: relative;
    transition: background 0.2s;
  }

  .toggle-thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    background: var(--text-primary);
    border-radius: 50%;
    transition: transform 0.2s;
  }

  :global([data-theme="light"]) .toggle-thumb {
    transform: translateX(16px);
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
    color: var(--text-secondary);
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
    color: var(--color-pass);
  }
  :global(.fail) {
    color: var(--color-fail);
  }
  :global(.error) {
    color: var(--color-error);
  }

  :global(button) {
    background: var(--accent);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    cursor: pointer;
    border-radius: 4px;
    font-size: 0.9rem;
  }

  :global(button:hover) {
    background: var(--accent-hover);
  }

  :global(button:disabled) {
    background: var(--bg-hover);
    cursor: not-allowed;
  }

  :global(textarea),
  :global(input[type="text"]) {
    background: var(--bg-input);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 0.5rem;
    border-radius: 4px;
    font-family: inherit;
    font-size: 0.9rem;
  }

  :global(textarea:focus),
  :global(input:focus) {
    outline: none;
    border-color: var(--accent);
  }

  /* Mobile menu button */
  .mobile-menu-btn {
    display: none;
    position: fixed;
    top: 1rem;
    left: 1rem;
    z-index: 1001;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    padding: 0.5rem 0.75rem;
    font-size: 1.25rem;
  }

  .mobile-menu-btn:hover {
    background: var(--bg-tertiary);
  }

  /* Responsive styles */
  @media (max-width: 768px) {
    .mobile-menu-btn {
      display: block;
    }

    nav {
      position: fixed;
      top: 0;
      left: 0;
      height: 100vh;
      width: 280px;
      transform: translateX(-100%);
      transition: transform 0.2s ease;
      z-index: 1000;
      padding-top: 4rem;
    }

    nav.open {
      transform: translateX(0);
    }

    main {
      padding: 1rem;
      padding-top: 4rem;
    }
  }

  @media (max-width: 480px) {
    nav {
      width: 100%;
    }

    main {
      padding: 0.75rem;
      padding-top: 4rem;
    }
  }
</style>
