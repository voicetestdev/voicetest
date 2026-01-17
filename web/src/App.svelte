<script lang="ts">
  import { currentView } from "./lib/stores";
  import AgentView from "./components/AgentView.svelte";
  import TestsView from "./components/TestsView.svelte";
  import RunsView from "./components/RunsView.svelte";
  import SettingsView from "./components/SettingsView.svelte";
</script>

<div class="app">
  <nav>
    <h1>voicetest</h1>
    <ul>
      <li>
        <button
          class:active={$currentView === "agents"}
          onclick={() => currentView.set("agents")}
        >
          Agents
        </button>
      </li>
      <li>
        <button
          class:active={$currentView === "tests"}
          onclick={() => currentView.set("tests")}
        >
          Tests
        </button>
      </li>
      <li>
        <button
          class:active={$currentView === "runs"}
          onclick={() => currentView.set("runs")}
        >
          Runs
        </button>
      </li>
      <li>
        <button
          class:active={$currentView === "settings"}
          onclick={() => currentView.set("settings")}
        >
          Settings
        </button>
      </li>
    </ul>
  </nav>

  <main>
    {#if $currentView === "agents"}
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
    width: 200px;
    background: #16213e;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  nav h1 {
    font-size: 1.25rem;
    margin: 0;
    color: #3b82f6;
  }

  nav ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  nav button {
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

  nav button:hover {
    background: #1a1a2e;
  }

  nav button.active {
    background: #3b82f6;
    color: white;
  }

  main {
    flex: 1;
    padding: 1.5rem;
    overflow: auto;
  }

  :global(.pass) { color: #4ade80; }
  :global(.fail) { color: #f87171; }
  :global(.error) { color: #fbbf24; }

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

  :global(textarea), :global(input[type="text"]) {
    background: #16213e;
    border: 1px solid #374151;
    color: #e8e8e8;
    padding: 0.5rem;
    border-radius: 4px;
    font-family: inherit;
    font-size: 0.9rem;
  }

  :global(textarea:focus), :global(input:focus) {
    outline: none;
    border-color: #3b82f6;
  }
</style>
