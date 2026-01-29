<script lang="ts">
  import { onMount } from "svelte";
  import {
    currentView,
    initStores,
    agents,
    currentAgentId,
    selectAgent,
    testCaseRecords,
    runHistory,
    loadRun,
    currentRunId,
  } from "./lib/stores";
  import { get } from "svelte/store";
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

  async function switchView(view: "config" | "tests" | "metrics" | "runs") {
    currentView.set(view);
    if (view === "runs") {
      const runs = get(runHistory);
      const currentRun = get(currentRunId);
      if (runs.length > 0 && !currentRun) {
        await loadRun(runs[0].id);
      }
    }
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
      <div class="nav-label">Agents</div>
      <ul class="agent-list">
        {#each $agents as agent}
          {@const isSelected = $currentAgentId === agent.id}
          <li>
            <button
              class="agent-btn"
              class:selected={isSelected}
              onclick={() => selectAgent(agent.id, "config")}
            >
              <span class="agent-name">{agent.name}</span>
            </button>
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
    {:else if $currentView === "settings"}
      <SettingsView />
    {:else if $currentAgentId}
      <div class="view-tabs">
        <button
          class="tab-item"
          class:active={$currentView === "config"}
          onclick={() => switchView("config")}
        >Config</button>
        <button
          class="tab-item"
          class:active={$currentView === "metrics"}
          onclick={() => switchView("metrics")}
        >Metrics</button>
        <button
          class="tab-item"
          class:active={$currentView === "tests"}
          onclick={() => switchView("tests")}
        >
          Tests
          {#if $testCaseRecords.length > 0}
            <span class="tab-count">{$testCaseRecords.length}</span>
          {/if}
        </button>
        <button
          class="tab-item"
          class:active={$currentView === "runs"}
          onclick={() => switchView("runs")}
        >
          Runs
          {#if $runHistory.length > 0}
            <span class="tab-count">{$runHistory.length}</span>
          {/if}
        </button>
      </div>
      <div class="view-content">
        {#if $currentView === "config"}
          <AgentView {theme} />
        {:else if $currentView === "tests"}
          <TestsView />
        {:else if $currentView === "metrics"}
          <MetricsView />
        {:else if $currentView === "runs"}
          <RunsView />
        {/if}
      </div>
    {:else}
      <div class="empty-state">
        <p>Select an agent from the sidebar or import a new one.</p>
      </div>
    {/if}
  </main>
</div>

<style>
  :global(:root) {
    /* GitHub Dark Theme */
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --bg-hover: #30363d;
    --bg-input: #0d1117;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    --border-color: #30363d;
    --accent: #238636;
    --accent-hover: #2ea043;
    --accent-blue: #1f6feb;
    --color-pass: #3fb950;
    --color-fail: #f85149;
    --color-error: #d29922;
    --status-pass-bg: rgba(63, 185, 80, 0.15);
    --status-fail-bg: rgba(248, 81, 73, 0.15);
    --status-error-bg: rgba(210, 153, 34, 0.15);
    --danger-bg: transparent;
    --danger-bg-hover: rgba(248, 81, 73, 0.15);
    --danger-text: #f85149;
    --danger-border: #f85149;
    /* Spacing */
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    /* Typography */
    --text-xs: 12px;
    --text-sm: 14px;
    /* Border radius */
    --radius-sm: 3px;
    --radius-md: 6px;
    /* Tab highlight */
    --tab-highlight: #f78166;
  }

  :global([data-theme="light"]) {
    --bg-primary: #ffffff;
    --bg-secondary: #f6f8fa;
    --bg-tertiary: #f6f8fa;
    --bg-hover: #eaeef2;
    --bg-input: #ffffff;
    --text-primary: #1f2328;
    --text-secondary: #656d76;
    --text-muted: #8b949e;
    --border-color: #d0d7de;
    --accent: #1f883d;
    --accent-hover: #1a7f37;
    --accent-blue: #0969da;
    --color-pass: #1a7f37;
    --color-fail: #cf222e;
    --color-error: #bf8700;
    --status-pass-bg: rgba(26, 127, 55, 0.15);
    --status-fail-bg: rgba(207, 34, 46, 0.15);
    --status-error-bg: rgba(191, 135, 0, 0.15);
    --danger-bg: transparent;
    --danger-bg-hover: rgba(207, 34, 46, 0.15);
    --danger-text: #cf222e;
    --danger-border: #cf222e;
    --tab-highlight: #fd8c73;
  }

  :global(body) {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
    font-size: var(--text-sm);
    line-height: 1.5;
    background: var(--bg-primary);
    color: var(--text-primary);
    transition: background 80ms ease-out, color 80ms ease-out;
  }

  :global(*) {
    box-sizing: border-box;
  }

  :global(::selection) {
    background: rgba(31, 111, 235, 0.3);
  }

  .app {
    display: flex;
    height: 100vh;
  }

  nav {
    width: 260px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
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

  .nav-label {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: var(--space-2) var(--space-2);
    margin-bottom: var(--space-1);
  }

  .agent-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .agent-btn {
    display: flex;
    align-items: center;
    width: 100%;
    text-align: left;
    padding: var(--space-2) var(--space-3);
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
    transition: background 80ms ease-out, color 80ms ease-out;
  }

  .agent-btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .agent-btn.selected {
    background: var(--bg-tertiary);
    color: var(--text-primary);
    font-weight: 500;
  }

  .agent-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }


  .nav-footer {
    display: flex;
    flex-direction: column;
    gap: 2px;
    border-top: 1px solid var(--border-color);
    padding-top: var(--space-4);
  }

  .nav-footer button {
    width: 100%;
    text-align: left;
    padding: var(--space-2) var(--space-3);
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
    transition: background 80ms ease-out, color 80ms ease-out;
  }

  .nav-footer button:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .nav-footer button.active {
    background: var(--bg-tertiary);
    color: var(--text-primary);
    font-weight: 500;
  }

  .import-btn {
    color: var(--accent) !important;
  }

  .import-btn:hover {
    color: var(--accent-hover) !important;
  }

  .import-btn.active {
    background: var(--accent) !important;
    color: #ffffff !important;
  }

  .theme-toggle {
    display: flex !important;
    align-items: center;
    justify-content: center;
    padding: var(--space-2) var(--space-3) !important;
    background: transparent !important;
  }

  .theme-toggle:hover {
    background: var(--bg-hover) !important;
  }

  .toggle-track {
    width: 36px;
    height: 20px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    position: relative;
    transition: background 80ms ease-out;
  }

  .toggle-thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    background: var(--text-secondary);
    border-radius: 50%;
    transition: transform 80ms ease-out, background 80ms ease-out;
  }

  :global([data-theme="light"]) .toggle-thumb {
    transform: translateX(16px);
    background: var(--text-primary);
  }

  main {
    flex: 1;
    padding: var(--space-4);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .view-tabs {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: var(--space-4);
    flex-shrink: 0;
  }

  .tab-item {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: var(--space-3) var(--space-4);
    margin-bottom: -1px;
    cursor: pointer;
    color: var(--text-secondary);
    font-size: var(--text-sm);
    display: flex;
    align-items: center;
    gap: var(--space-2);
    transition: color 80ms ease-out, border-color 80ms ease-out;
  }

  .tab-item:hover {
    color: var(--text-primary);
    background: transparent;
  }

  .tab-item.active {
    color: var(--text-primary);
    font-weight: 600;
    border-bottom-color: var(--tab-highlight);
    background: transparent;
  }

  .tab-count {
    font-size: var(--text-xs);
    background: var(--bg-tertiary);
    padding: 0.1rem 0.4rem;
    border-radius: 9999px;
    color: var(--text-muted);
  }

  .tab-item.active .tab-count {
    background: var(--bg-hover);
    color: var(--text-secondary);
  }

  .view-content {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-secondary);
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
    color: var(--color-fail);
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
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    border: 1px solid var(--border-color);
    padding: 0.5rem 1rem;
    cursor: pointer;
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
    transition: background 80ms ease-out, border-color 80ms ease-out, color 80ms ease-out;
  }

  :global(button:hover) {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  :global(button:disabled) {
    background: var(--bg-tertiary);
    color: var(--text-muted);
    border-color: var(--border-color);
    cursor: not-allowed;
    opacity: 0.6;
  }

  :global(button.btn-primary),
  :global(.btn-primary) {
    background: var(--accent);
    color: #ffffff;
    border-color: var(--accent);
  }

  :global(button.btn-primary:hover),
  :global(.btn-primary:hover) {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
  }

  :global(button.btn-danger),
  :global(.btn-danger) {
    background: transparent;
    color: var(--danger-text);
    border-color: var(--border-color);
  }

  :global(button.btn-danger:hover),
  :global(.btn-danger:hover) {
    background: var(--danger-bg-hover);
    border-color: var(--danger-border);
  }

  :global(textarea),
  :global(input[type="text"]),
  :global(input[type="number"]),
  :global(input[type="password"]),
  :global(select) {
    background: var(--bg-input);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: var(--space-2);
    border-radius: var(--radius-md);
    font-family: inherit;
    font-size: var(--text-sm);
    transition: border-color 80ms ease-out, box-shadow 80ms ease-out;
  }

  :global(textarea:focus),
  :global(input:focus),
  :global(select:focus) {
    outline: none;
    border-color: var(--accent-blue);
    box-shadow: 0 0 0 3px rgba(31, 111, 235, 0.3);
  }

  /* Mobile menu button */
  .mobile-menu-btn {
    display: none;
    position: fixed;
    top: var(--space-4);
    left: var(--space-4);
    z-index: 1001;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    padding: var(--space-2) var(--space-3);
    font-size: 1.25rem;
    border-radius: var(--radius-md);
    color: var(--text-primary);
  }

  .mobile-menu-btn:hover {
    background: var(--bg-hover);
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
      transition: transform 200ms ease;
      z-index: 1000;
      padding-top: 4rem;
    }

    nav.open {
      transform: translateX(0);
    }

    main {
      padding: var(--space-4);
      padding-top: 4rem;
    }

    .view-tabs {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }

    .tab-item {
      padding: var(--space-2) var(--space-3);
      white-space: nowrap;
    }
  }

  @media (max-width: 480px) {
    nav {
      width: 100%;
    }

    main {
      padding: var(--space-3);
      padding-top: 4rem;
    }
  }
</style>
