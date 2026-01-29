<script lang="ts">
  import { api } from "../lib/api";
  import { currentAgentId } from "../lib/stores";
  import type { GlobalMetric, MetricsConfig } from "../lib/types";

  let config = $state<MetricsConfig>({
    threshold: 0.7,
    global_metrics: [],
  });
  let loading = $state(false);
  let saving = $state(false);
  let error = $state("");
  let saveTimeout: ReturnType<typeof setTimeout> | null = null;

  let newMetricName = $state("");
  let newMetricCriteria = $state("");
  let newMetricThreshold = $state<string>("");

  $effect(() => {
    if ($currentAgentId) {
      loadConfig($currentAgentId);
    }
  });

  async function loadConfig(agentId: string) {
    loading = true;
    error = "";
    try {
      config = await api.getMetricsConfig(agentId);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    loading = false;
  }

  async function saveConfig() {
    if (!$currentAgentId) return;
    saving = true;
    error = "";
    try {
      config = await api.updateMetricsConfig($currentAgentId, config);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    saving = false;
  }

  function debouncedSave() {
    if (saveTimeout) clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => saveConfig(), 500);
  }

  async function addMetric() {
    if (!newMetricName.trim() || !newMetricCriteria.trim()) return;

    const threshold = newMetricThreshold.trim()
      ? parseFloat(newMetricThreshold)
      : null;

    const newMetric: GlobalMetric = {
      name: newMetricName.trim(),
      criteria: newMetricCriteria.trim(),
      threshold: threshold,
      enabled: true,
    };

    config.global_metrics = [...config.global_metrics, newMetric];
    newMetricName = "";
    newMetricCriteria = "";
    newMetricThreshold = "";
    await saveConfig();
  }

  async function removeMetric(index: number) {
    config.global_metrics = config.global_metrics.filter((_, i) => i !== index);
    await saveConfig();
  }

  async function toggleMetric(index: number) {
    config.global_metrics = config.global_metrics.map((m, i) =>
      i === index ? { ...m, enabled: !m.enabled } : m
    );
    await saveConfig();
  }

  function updateMetricThreshold(index: number, value: string) {
    const threshold = value.trim() ? parseFloat(value) : null;
    config.global_metrics = config.global_metrics.map((m, i) =>
      i === index ? { ...m, threshold } : m
    );
    debouncedSave();
  }
</script>

<div class="metrics-view">
  <div class="header">
    <h2>Metrics</h2>
    {#if saving}
      <span class="save-indicator">Saving...</span>
    {/if}
  </div>

  {#if loading}
    <p>Loading metrics configuration...</p>
  {:else}
    <section class="settings-form">
      <h3>Pass Threshold</h3>
      <p class="hint">
        Minimum score (0-1) for metrics to pass. Applied to all metrics unless overridden.
      </p>

      <div class="form-group">
        <label for="threshold">Default Threshold</label>
        <input
          id="threshold"
          type="number"
          bind:value={config.threshold}
          oninput={debouncedSave}
          min={0}
          max={1}
          step={0.05}
        />
      </div>
    </section>

    <section class="settings-form">
      <h3>Global Metrics</h3>
      <p class="hint">
        Metrics that run on every test for this agent. Use for compliance checks or universal requirements.
      </p>

      {#if config.global_metrics.length > 0}
        <div class="metric-list">
          {#each config.global_metrics as metric, index}
            <div class="metric-item" class:disabled={!metric.enabled}>
              <div class="metric-header">
                <button
                  class="toggle-btn"
                  class:enabled={metric.enabled}
                  onclick={() => toggleMetric(index)}
                  title={metric.enabled ? "Disable metric" : "Enable metric"}
                >
                  {metric.enabled ? "ON" : "OFF"}
                </button>
                <span class="metric-name">{metric.name}</span>
                <div class="metric-threshold">
                  <label for={`threshold-${index}`}>Threshold:</label>
                  <input
                    id={`threshold-${index}`}
                    type="number"
                    value={metric.threshold ?? ""}
                    oninput={(e) => updateMetricThreshold(index, e.currentTarget.value)}
                    placeholder={String(config.threshold)}
                    min={0}
                    max={1}
                    step={0.05}
                  />
                </div>
                <button class="small danger" onclick={() => removeMetric(index)}>Delete</button>
              </div>
              <div class="metric-criteria">{metric.criteria}</div>
            </div>
          {/each}
        </div>
      {:else}
        <p class="empty-state">No global metrics configured.</p>
      {/if}

      <div class="add-metric-form">
        <h4>Add Global Metric</h4>
        <div class="form-row">
          <div class="form-group">
            <label for="new-name">Name</label>
            <input
              id="new-name"
              type="text"
              bind:value={newMetricName}
              placeholder="e.g., HIPAA Compliance"
            />
          </div>
          <div class="form-group threshold-field">
            <label for="new-threshold">Threshold (optional)</label>
            <input
              id="new-threshold"
              type="number"
              bind:value={newMetricThreshold}
              placeholder={String(config.threshold)}
              min={0}
              max={1}
              step={0.05}
            />
          </div>
        </div>
        <div class="form-group">
          <label for="new-criteria">Criteria</label>
          <textarea
            id="new-criteria"
            bind:value={newMetricCriteria}
            placeholder="e.g., Agent must verify patient identity before sharing any medical information"
            rows={3}
          ></textarea>
        </div>
        <button
          class="secondary"
          onclick={addMetric}
          disabled={!newMetricName.trim() || !newMetricCriteria.trim()}
        >
          Add Metric
        </button>
      </div>
    </section>

    {#if error}
      <p class="error-message">{error}</p>
    {/if}
  {/if}
</div>

<style>
  .metrics-view {
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

  h3 {
    margin-top: 0;
    font-size: 1rem;
    color: var(--text-secondary);
  }

  h4 {
    margin: 1.5rem 0 1rem 0;
    font-size: 0.9rem;
    color: var(--text-secondary);
    border-top: 1px solid var(--border-color);
    padding-top: 1rem;
  }

  .settings-form {
    background: var(--bg-secondary);
    padding: var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    margin-bottom: 1.5rem;
  }

  .form-group {
    margin-bottom: 1rem;
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
  .form-group input[type="number"],
  .form-group textarea {
    width: 100%;
  }

  .form-row {
    display: flex;
    gap: 1rem;
  }

  .form-row .form-group {
    flex: 1;
  }

  .form-row .threshold-field {
    flex: 0 0 150px;
  }

  .hint {
    display: block;
    margin-top: 0.25rem;
    margin-bottom: 1rem;
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .metric-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .metric-item {
    background: var(--bg-tertiary);
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    transition: background 80ms ease-out;
  }

  .metric-item.disabled {
    opacity: 0.5;
  }

  .metric-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .toggle-btn {
    padding: 0.15rem 0.4rem;
    font-size: var(--text-xs);
    font-weight: 600;
    border-radius: 9999px;
    background: var(--status-fail-bg);
    color: var(--color-fail);
    border: 1px solid rgba(248, 81, 73, 0.3);
    min-width: 36px;
  }

  .toggle-btn.enabled {
    background: var(--status-pass-bg);
    color: var(--color-pass);
    border-color: rgba(63, 185, 80, 0.3);
  }

  .toggle-btn:hover {
    opacity: 0.9;
  }

  .metric-name {
    font-weight: 500;
    flex: 1;
  }

  .metric-threshold {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .metric-threshold input {
    width: 70px;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
  }

  .metric-threshold label {
    margin: 0;
  }

  .metric-criteria {
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .empty-state {
    color: var(--text-muted);
    font-style: italic;
    margin: 1rem 0;
  }

  .add-metric-form {
    margin-top: 1rem;
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

  .error-message {
    color: #f87171;
    margin: 0 0 1rem 0;
  }

  textarea {
    resize: vertical;
    min-height: 60px;
  }
</style>
