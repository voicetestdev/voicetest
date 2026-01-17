<script lang="ts">
  import { api } from "../lib/api";
  import { settings } from "../lib/stores";
  import type { Settings } from "../lib/types";

  let localSettings = $state<Settings>({
    models: {
      agent: "openai/gpt-4o-mini",
      simulator: "openai/gpt-4o-mini",
      judge: "openai/gpt-4o-mini",
    },
    run: {
      max_turns: 20,
      verbose: false,
    },
  });
  let loading = $state(false);
  let saving = $state(false);
  let error = $state("");
  let success = $state("");

  $effect(() => {
    loadSettings();
  });

  async function loadSettings() {
    loading = true;
    error = "";
    try {
      const s = await api.getSettings();
      settings.set(s);
      localSettings = structuredClone(s);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    loading = false;
  }

  async function saveSettings() {
    saving = true;
    error = "";
    success = "";

    try {
      const updated = await api.updateSettings(localSettings);
      settings.set(updated);
      localSettings = structuredClone(updated);
      success = "Settings saved";
      setTimeout(() => (success = ""), 3000);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }

    saving = false;
  }

  function resetToDefaults() {
    localSettings = {
      models: {
        agent: "openai/gpt-4o-mini",
        simulator: "openai/gpt-4o-mini",
        judge: "openai/gpt-4o-mini",
      },
      run: {
        max_turns: 20,
        verbose: false,
      },
    };
  }
</script>

<div class="settings-view">
  <h2>Settings</h2>

  {#if loading}
    <p>Loading settings...</p>
  {:else}
    <section class="settings-form">
      <h3>Model Configuration</h3>
      <p class="hint">
        Use <a href="https://docs.litellm.ai/docs/providers" target="_blank">LiteLLM format</a>
        (e.g., openai/gpt-4o, anthropic/claude-3-haiku, ollama_chat/llama3)
      </p>

      <div class="form-group">
        <label for="agent-model">Agent Model</label>
        <input
          id="agent-model"
          type="text"
          bind:value={localSettings.models.agent}
          placeholder="openai/gpt-4o-mini"
        />
        <span class="hint">Model used to generate agent responses</span>
      </div>

      <div class="form-group">
        <label for="simulator-model">Simulator Model</label>
        <input
          id="simulator-model"
          type="text"
          bind:value={localSettings.models.simulator}
          placeholder="openai/gpt-4o-mini"
        />
        <span class="hint">Model used to simulate user behavior</span>
      </div>

      <div class="form-group">
        <label for="judge-model">Judge Model</label>
        <input
          id="judge-model"
          type="text"
          bind:value={localSettings.models.judge}
          placeholder="openai/gpt-4o-mini"
        />
        <span class="hint">Model used to evaluate test metrics</span>
      </div>
    </section>

    <section class="settings-form">
      <h3>Run Configuration</h3>

      <div class="form-group">
        <label for="max-turns">Max Turns</label>
        <input
          id="max-turns"
          type="number"
          bind:value={localSettings.run.max_turns}
          min={1}
          max={100}
        />
        <span class="hint">Maximum conversation turns per test</span>
      </div>

      <div class="form-group checkbox">
        <input id="verbose" type="checkbox" bind:checked={localSettings.run.verbose} />
        <label for="verbose">Verbose output</label>
      </div>
    </section>

    <div class="button-row">
      <button onclick={saveSettings} disabled={saving}>
        {saving ? "Saving..." : "Save Settings"}
      </button>
      <button class="secondary" onclick={resetToDefaults}>
        Reset to Defaults
      </button>
      <button class="secondary" onclick={loadSettings}>
        Reload
      </button>
    </div>

    {#if error}
      <p class="error-message">{error}</p>
    {/if}

    {#if success}
      <p class="success-message">{success}</p>
    {/if}

    <section class="info-section">
      <h3>Environment Variables</h3>
      <p class="hint">
        API keys are set via environment variables:
      </p>
      <ul class="env-list">
        <li><code>OPENAI_API_KEY</code> - OpenAI API key</li>
        <li><code>ANTHROPIC_API_KEY</code> - Anthropic API key</li>
        <li><code>GEMINI_API_KEY</code> - Google Gemini API key</li>
      </ul>
    </section>
  {/if}
</div>

<style>
  .settings-view {
    max-width: 600px;
  }

  h2 {
    margin-top: 0;
  }

  h3 {
    margin-top: 0;
    font-size: 1rem;
    color: #9ca3af;
  }

  .settings-form {
    background: #16213e;
    padding: 1.5rem;
    border-radius: 8px;
    margin-bottom: 1.5rem;
  }

  .form-group {
    margin-bottom: 1.25rem;
  }

  .form-group label {
    display: block;
    margin-bottom: 0.25rem;
    color: #9ca3af;
    font-size: 0.85rem;
  }

  .form-group input[type="text"],
  .form-group input[type="number"] {
    width: 100%;
  }

  .form-group.checkbox {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .form-group.checkbox label {
    margin: 0;
  }

  .hint {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.75rem;
    color: #6b7280;
  }

  .hint a {
    color: #3b82f6;
  }

  .button-row {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }

  .secondary {
    background: #374151;
  }

  .secondary:hover {
    background: #4b5563;
  }

  .error-message {
    color: #f87171;
    margin: 0 0 1rem 0;
  }

  .success-message {
    color: #4ade80;
    margin: 0 0 1rem 0;
  }

  .info-section {
    background: #16213e;
    padding: 1rem;
    border-radius: 8px;
  }

  .env-list {
    list-style: none;
    padding: 0;
    margin: 0.5rem 0 0 0;
  }

  .env-list li {
    margin-bottom: 0.25rem;
  }

  .env-list code {
    background: #1a1a2e;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
    font-size: 0.85rem;
  }
</style>
