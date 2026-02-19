<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import { settings } from "../lib/stores";
  import type { Settings } from "../lib/types";

  let localSettings = $state<Settings>({
    models: {
      agent: null,
      simulator: null,
      judge: null,
    },
    run: {
      max_turns: 20,
      verbose: false,
      flow_judge: false,
      streaming: false,
      test_model_precedence: false,
      audio_eval: false,
    },
    audio: {
      tts_url: "http://localhost:8002/v1",
      stt_url: "http://localhost:8001/v1",
    },
    env: {},
  });

  // Helper to handle null model values in inputs
  function modelValue(value: string | null): string {
    return value ?? "";
  }

  function setModel(field: "agent" | "simulator" | "judge", value: string) {
    const trimmed = value.trim();
    localSettings.models[field] = trimmed === "" ? null : trimmed;
    debouncedSave();
  }
  let loading = $state(false);
  let saving = $state(false);
  let saved = $state(false);
  let error = $state("");
  let newEnvKey = $state("");
  let newEnvValue = $state("");
  let saveTimeout: ReturnType<typeof setTimeout> | null = null;

  onMount(() => {
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
    saved = false;
    error = "";

    try {
      const updated = await api.updateSettings(localSettings);
      settings.set(updated);
      saved = true;
      setTimeout(() => { saved = false; }, 2000);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }

    saving = false;
  }

  function debouncedSave() {
    if (saveTimeout) clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => saveSettings(), 500);
  }

  async function addEnvVar() {
    if (newEnvKey.trim() && newEnvValue.trim()) {
      localSettings.env = {
        ...localSettings.env,
        [newEnvKey.trim()]: newEnvValue.trim(),
      };
      newEnvKey = "";
      newEnvValue = "";
      await saveSettings();
    }
  }

  async function removeEnvVar(key: string) {
    const { [key]: _, ...rest } = localSettings.env;
    localSettings.env = rest;
    await saveSettings();
  }

  function maskValue(value: string): string {
    if (value.length <= 8) return "****";
    return value.substring(0, 4) + "****" + value.substring(value.length - 4);
  }
</script>

<div class="settings-view">
  <div class="header">
    <h2>Settings</h2>
    {#if saving}
      <span class="save-indicator">Saving...</span>
    {:else if saved}
      <span class="save-indicator saved">Saved</span>
    {/if}
  </div>

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
          value={modelValue(localSettings.models.agent)}
          oninput={(e) => setModel("agent", e.currentTarget.value)}
          placeholder="Leave empty to use agent/test defaults"
        />
        <span class="hint">Model used to generate agent responses. Leave empty to use agent's imported default.</span>
      </div>

      <div class="form-group">
        <label for="simulator-model">Simulator Model</label>
        <input
          id="simulator-model"
          type="text"
          value={modelValue(localSettings.models.simulator)}
          oninput={(e) => setModel("simulator", e.currentTarget.value)}
          placeholder="Leave empty to use test defaults"
        />
        <span class="hint">Model used to simulate user behavior. Leave empty to use test's llm_model.</span>
      </div>

      <div class="form-group">
        <label for="judge-model">Judge Model</label>
        <input
          id="judge-model"
          type="text"
          value={modelValue(localSettings.models.judge)}
          oninput={(e) => setModel("judge", e.currentTarget.value)}
          placeholder="Leave empty to use default"
        />
        <span class="hint">Model used to evaluate test metrics.</span>
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
          oninput={debouncedSave}
          onchange={saveSettings}
          min={1}
          max={100}
        />
        <span class="hint">Maximum conversation turns per test</span>
      </div>

      <div class="form-group checkbox">
        <input
          id="verbose"
          type="checkbox"
          bind:checked={localSettings.run.verbose}
          onchange={saveSettings}
        />
        <label for="verbose">Verbose output</label>
      </div>

      <div class="form-group checkbox">
        <input
          id="flow-judge"
          type="checkbox"
          bind:checked={localSettings.run.flow_judge}
          onchange={saveSettings}
        />
        <label for="flow-judge">Flow judge</label>
        <span class="hint checkbox-hint">LLM evaluates if node transitions were logical</span>
      </div>

      <div class="form-group checkbox">
        <input
          id="streaming"
          type="checkbox"
          bind:checked={localSettings.run.streaming}
          onchange={saveSettings}
        />
        <label for="streaming">Streaming</label>
        <span class="hint checkbox-hint">Stream tokens as they are generated (experimental)</span>
      </div>

      <div class="form-group checkbox">
        <input
          id="test-model-precedence"
          type="checkbox"
          bind:checked={localSettings.run.test_model_precedence}
          onchange={saveSettings}
        />
        <label for="test-model-precedence">Test/agent models take precedence</label>
        <span class="hint checkbox-hint">When enabled, agent and test LLM settings override global settings</span>
      </div>

      <div class="form-group checkbox">
        <input
          id="audio-eval"
          type="checkbox"
          bind:checked={localSettings.run.audio_eval}
          onchange={saveSettings}
        />
        <label for="audio-eval">Audio evaluation</label>
        <span class="hint checkbox-hint">Auto-run TTS→STT round-trip on every test (requires voicetest up)</span>
      </div>
    </section>

    {#if error}
      <p class="error-message">{error}</p>
    {/if}

    <section class="settings-form">
      <h3>Environment Variables</h3>
      <p class="hint">
        Set API keys for LLM providers. These are applied when running tests, overriding system env vars.
        Stored in .voicetest.toml (add to .gitignore).
      </p>
      <p class="hint">
        Common keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, AZURE_API_KEY, COHERE_API_KEY
      </p>

      {#if Object.keys(localSettings.env).length > 0}
        <div class="env-list">
          {#each Object.entries(localSettings.env) as [key, value]}
            <div class="env-item">
              <code class="env-key">{key}</code>
              <span class="env-value">{maskValue(value)}</span>
              <button class="small danger" onclick={() => removeEnvVar(key)}>Remove</button>
            </div>
          {/each}
        </div>
      {/if}

      <div class="env-add">
        <input
          type="text"
          bind:value={newEnvKey}
          placeholder="Variable name (e.g., OPENAI_API_KEY)"
          class="env-input"
        />
        <input
          type="password"
          bind:value={newEnvValue}
          placeholder="Value"
          class="env-input"
        />
        <button class="secondary" onclick={addEnvVar} disabled={!newEnvKey.trim() || !newEnvValue.trim()}>
          Add
        </button>
      </div>
    </section>
  {/if}
</div>

<style>
  .settings-view {
    overflow-y: auto;
    flex: 1;
  }

  .header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  h2 {
    margin: 0;
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

  .settings-form {
    background: var(--bg-secondary);
    padding: var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    margin-bottom: 1.5rem;
  }

  .form-group {
    margin-bottom: 1.25rem;
  }

  .form-group:last-child {
    margin-bottom: 0;
  }

  .form-group label {
    display: block;
    margin-bottom: 0.25rem;
    color: var(--text-secondary);
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

  .checkbox-hint {
    margin: 0;
    margin-left: auto;
  }

  .hint {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .hint a {
    color: #3b82f6;
  }

  .secondary {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
  }

  .secondary:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
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

  .env-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .env-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: var(--bg-tertiary);
    padding: var(--space-3);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
  }

  .env-key {
    background: var(--bg-hover);
    padding: 0.2rem 0.5rem;
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    min-width: 180px;
  }

  .env-value {
    flex: 1;
    color: var(--text-muted);
    font-family: monospace;
    font-size: 0.85rem;
  }

  .env-add {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .env-input {
    flex: 1;
  }

  .small {
    padding: 0.2rem 0.4rem;
    font-size: var(--text-xs);
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
</style>
