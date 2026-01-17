<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
    testCases,
    currentRun,
    isRunning,
    selectedTestId,
    selectedResult,
    runSummary,
  } from "../lib/stores";
  import type { RunOptions, TestResult } from "../lib/types";

  let options = $state<Partial<RunOptions>>({
    max_turns: 10,
    timeout_seconds: 60,
  });
  let error = $state("");

  async function runAllTests() {
    if (!$agentGraph || $testCases.length === 0) return;

    isRunning.set(true);
    error = "";

    try {
      const run = await api.runTests($agentGraph, $testCases, options);
      currentRun.set(run);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }

    isRunning.set(false);
  }

  async function runSingleTest() {
    if (!$agentGraph || !$selectedTestId) return;

    const test = $testCases.find((t) => t.name === $selectedTestId);
    if (!test) return;

    isRunning.set(true);
    error = "";

    try {
      const result = await api.runSingleTest($agentGraph, test, options);
      currentRun.update((run) => {
        if (!run) {
          return {
            run_id: crypto.randomUUID(),
            started_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            results: [result],
            passed_count: result.status === "pass" ? 1 : 0,
            failed_count: result.status !== "pass" ? 1 : 0,
          };
        }
        const existingIdx = run.results.findIndex((r) => r.test_id === result.test_id);
        const newResults =
          existingIdx >= 0
            ? run.results.map((r, i) => (i === existingIdx ? result : r))
            : [...run.results, result];
        return {
          ...run,
          results: newResults,
          passed_count: newResults.filter((r) => r.status === "pass").length,
          failed_count: newResults.filter((r) => r.status !== "pass").length,
        };
      });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }

    isRunning.set(false);
  }

  function clearRun() {
    currentRun.set(null);
    selectedTestId.set(null);
  }

  function getStatusClass(result: TestResult): string {
    if (result.status === "error") return "error";
    return result.status === "pass" ? "pass" : "fail";
  }
</script>

<div class="runs-view">
  <h2>Test Runs</h2>

  <div class="layout">
    <section class="controls">
      <h3>Run Options</h3>

      <div class="form-group">
        <label for="max-turns">Max Turns</label>
        <input
          id="max-turns"
          type="number"
          bind:value={options.max_turns}
          min={1}
          max={100}
        />
      </div>

      <div class="form-group">
        <label for="timeout">Timeout (seconds)</label>
        <input
          id="timeout"
          type="number"
          bind:value={options.timeout_seconds}
          min={1}
          max={300}
        />
      </div>

      <div class="button-row">
        <button
          onclick={runAllTests}
          disabled={$isRunning || !$agentGraph || $testCases.length === 0}
        >
          {$isRunning ? "Running..." : "Run All Tests"}
        </button>
        <button
          class="secondary"
          onclick={runSingleTest}
          disabled={$isRunning || !$agentGraph || !$selectedTestId}
        >
          Run Selected
        </button>
      </div>

      {#if !$agentGraph}
        <p class="warning">Import an agent first</p>
      {:else if $testCases.length === 0}
        <p class="warning">Add test cases first</p>
      {/if}

      {#if error}
        <p class="error-message">{error}</p>
      {/if}
    </section>

    <section class="results">
      <div class="results-header">
        <h3>Results</h3>
        {#if $runSummary}
          <div class="summary">
            <span class="pass">{$runSummary.passed} passed</span>
            <span class="fail">{$runSummary.failed} failed</span>
            <span>/ {$runSummary.total} total</span>
          </div>
        {/if}
        {#if $currentRun}
          <button class="small secondary" onclick={clearRun}>Clear</button>
        {/if}
      </div>

      {#if !$currentRun}
        <p class="empty">No results yet</p>
      {:else}
        <ul class="results-list">
          {#each $currentRun.results as result}
            <li class:selected={$selectedTestId === result.test_id}>
              <button
                type="button"
                class="result-select-btn"
                onclick={() => selectedTestId.set(result.test_id)}
              >
                <span class="status {getStatusClass(result)}">
                  {result.status === "error" ? "ERR" : result.status === "pass" ? "PASS" : "FAIL"}
                </span>
                <span class="test-name">{result.test_id}</span>
                <span class="turns">{result.transcript.length} turns</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section class="detail">
      <h3>Detail View</h3>
      {#if !$selectedResult}
        <p class="empty">Select a result to view details</p>
      {:else}
        <div class="result-detail">
          <div class="info-row">
            <span class="label">Test:</span>
            <span>{$selectedResult.test_id}</span>
          </div>
          <div class="info-row">
            <span class="label">Status:</span>
            <span class={getStatusClass($selectedResult)}>
              {$selectedResult.status === "error"
                ? "Error"
                : $selectedResult.status === "pass"
                  ? "Passed"
                  : "Failed"}
            </span>
          </div>
          <div class="info-row">
            <span class="label">Duration:</span>
            <span>{$selectedResult.duration_ms}ms</span>
          </div>

          {#if $selectedResult.models_used}
            <h4>Models Used</h4>
            <div class="models-used">
              <div class="model-row">
                <span class="label">Agent:</span>
                <code>{$selectedResult.models_used.agent}</code>
              </div>
              <div class="model-row">
                <span class="label">Simulator:</span>
                <code>{$selectedResult.models_used.simulator}</code>
              </div>
              <div class="model-row">
                <span class="label">Judge:</span>
                <code>{$selectedResult.models_used.judge}</code>
              </div>
            </div>

            {#if $selectedResult.model_overrides && $selectedResult.model_overrides.length > 0}
              <div class="overrides">
                {#each $selectedResult.model_overrides as override}
                  <div class="override-item">
                    <span class="override-icon">⚠</span>
                    <span class="override-text">
                      <strong>{override.role}:</strong>
                      <code>{override.requested}</code> → <code>{override.actual}</code>
                      <span class="override-reason">({override.reason})</span>
                    </span>
                  </div>
                {/each}
              </div>
            {/if}
          {/if}

          {#if $selectedResult.error_message}
            <div class="error-box">
              <strong>Error:</strong>
              <pre>{$selectedResult.error_message}</pre>
            </div>
          {/if}

          <h4>Transcript</h4>
          <div class="transcript">
            {#each $selectedResult.transcript as msg}
              <div class="message {msg.role}">
                <span class="role">{msg.role}</span>
                <span class="content">{msg.content}</span>
              </div>
            {/each}
          </div>

          {#if $selectedResult.metric_results.length > 0}
            <h4>Metrics</h4>
            <ul class="metrics">
              {#each $selectedResult.metric_results as metric}
                <li class={metric.passed ? "pass" : "fail"}>
                  <span class="metric-name">{metric.metric}</span>
                  <span class="metric-passed">{metric.passed ? "Pass" : "Fail"}</span>
                  {#if metric.reasoning}
                    <span class="metric-reason">{metric.reasoning}</span>
                  {/if}
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}
    </section>
  </div>
</div>

<style>
  .runs-view {
    max-width: 1400px;
  }

  h2 {
    margin-top: 0;
  }

  h3 {
    margin-top: 0;
    font-size: 1rem;
    color: #9ca3af;
  }

  h4 {
    font-size: 0.9rem;
    color: #9ca3af;
    margin: 1rem 0 0.5rem 0;
  }

  .layout {
    display: grid;
    grid-template-columns: 250px 1fr 1fr;
    gap: 1.5rem;
  }

  .controls {
    background: #16213e;
    padding: 1rem;
    border-radius: 8px;
    height: fit-content;
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-group label {
    display: block;
    margin-bottom: 0.25rem;
    color: #9ca3af;
    font-size: 0.85rem;
  }

  .form-group input[type="number"] {
    width: 100%;
  }

  .button-row {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .warning {
    color: #fbbf24;
    font-size: 0.85rem;
    margin: 0.5rem 0 0 0;
  }

  .error-message {
    color: #f87171;
    font-size: 0.85rem;
    margin: 0.5rem 0 0 0;
  }

  .results {
    background: #16213e;
    padding: 1rem;
    border-radius: 8px;
  }

  .results-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .results-header h3 {
    margin: 0;
  }

  .summary {
    display: flex;
    gap: 0.5rem;
    font-size: 0.85rem;
  }

  .results-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    max-height: 500px;
    overflow-y: auto;
  }

  .results-list li {
    background: #1a1a2e;
    border-radius: 4px;
    border: 1px solid transparent;
  }

  .results-list li:hover {
    border-color: #374151;
  }

  .results-list li.selected {
    border-color: #3b82f6;
  }

  .result-select-btn {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.5rem;
    background: transparent;
    border: none;
    cursor: pointer;
    color: inherit;
    text-align: left;
  }

  .result-select-btn:hover {
    background: transparent;
  }

  .status {
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.2rem 0.4rem;
    border-radius: 3px;
    background: #374151;
  }

  .test-name {
    flex: 1;
  }

  .turns {
    color: #6b7280;
    font-size: 0.8rem;
  }

  .small {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }

  .secondary {
    background: #374151;
  }

  .secondary:hover {
    background: #4b5563;
  }

  .empty {
    color: #6b7280;
    font-style: italic;
  }

  .detail {
    background: #16213e;
    padding: 1rem;
    border-radius: 8px;
    max-height: 600px;
    overflow-y: auto;
  }

  .result-detail {
    font-size: 0.9rem;
  }

  .info-row {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.25rem;
  }

  .label {
    color: #9ca3af;
    min-width: 80px;
  }

  .error-box {
    background: #7f1d1d;
    padding: 0.75rem;
    border-radius: 4px;
    margin-top: 0.5rem;
  }

  .error-box pre {
    margin: 0.5rem 0 0 0;
    white-space: pre-wrap;
    font-size: 0.8rem;
  }

  .transcript {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-height: 300px;
    overflow-y: auto;
  }

  .message {
    padding: 0.5rem;
    border-radius: 4px;
    background: #1a1a2e;
  }

  .message.user {
    border-left: 3px solid #3b82f6;
  }

  .message.assistant {
    border-left: 3px solid #10b981;
  }

  .role {
    font-size: 0.75rem;
    color: #9ca3af;
    text-transform: uppercase;
    display: block;
    margin-bottom: 0.25rem;
  }

  .content {
    white-space: pre-wrap;
  }

  .metrics {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .metrics li {
    padding: 0.5rem;
    background: #1a1a2e;
    border-radius: 4px;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .metric-name {
    font-weight: 500;
  }

  .metric-score {
    color: #9ca3af;
  }

  .metric-reason {
    width: 100%;
    font-size: 0.85rem;
    color: #9ca3af;
  }

  .models-used {
    background: #1a1a2e;
    padding: 0.5rem;
    border-radius: 4px;
    margin-bottom: 0.5rem;
  }

  .model-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.25rem;
  }

  .model-row:last-child {
    margin-bottom: 0;
  }

  .model-row code {
    background: #374151;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-size: 0.8rem;
  }

  .overrides {
    background: #78350f;
    padding: 0.5rem;
    border-radius: 4px;
    margin-top: 0.5rem;
  }

  .override-item {
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    margin-bottom: 0.25rem;
  }

  .override-item:last-child {
    margin-bottom: 0;
  }

  .override-icon {
    color: #fbbf24;
  }

  .override-text {
    font-size: 0.8rem;
  }

  .override-text code {
    background: #1a1a2e;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
  }

  .override-reason {
    color: #d1d5db;
    font-style: italic;
  }
</style>
