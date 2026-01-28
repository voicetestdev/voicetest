<script lang="ts">
  import { api } from "../lib/api";
  import {
    currentRunWithResults,
    currentRunId,
    runHistory,
    cancelTest,
    retryStatus,
  } from "../lib/stores";
  import type { RunResultRecord, Message, MetricResult, ModelsUsed } from "../lib/types";

  let selectedResultId = $state<string | null>(null);
  let deleting = $state(false);

  // Auto-select the first running test so user can see streaming transcript
  $effect(() => {
    const results = $currentRunWithResults?.results ?? [];
    const runningResult = results.find((r) => r.status === "running");
    if (runningResult && selectedResultId !== runningResult.id) {
      // Only auto-select if nothing is selected or current selection is completed
      const currentSelection = results.find((r) => r.id === selectedResultId);
      if (!currentSelection || currentSelection.status !== "running") {
        selectedResultId = runningResult.id;
      }
    }
  });

  function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleString();
  }

  function parseTranscript(json: string | null): Message[] {
    if (!json) return [];
    try {
      return JSON.parse(json);
    } catch {
      return [];
    }
  }

  function parseMetrics(json: string | null): MetricResult[] {
    if (!json) return [];
    try {
      return JSON.parse(json);
    } catch {
      return [];
    }
  }

  function parseModelsUsed(json: string | null): ModelsUsed | null {
    if (!json) return null;
    try {
      return JSON.parse(json);
    } catch {
      return null;
    }
  }

  function getStatusClass(status: string): string {
    if (status === "running") return "running";
    if (status === "error") return "error";
    if (status === "cancelled") return "cancelled";
    return status === "pass" ? "pass" : "fail";
  }

  function getRunSummary(results: RunResultRecord[]): { passed: number; failed: number; total: number } {
    const passed = results.filter((r) => r.status === "pass").length;
    const failed = results.filter((r) => r.status !== "pass").length;
    return { passed, failed, total: results.length };
  }

  async function deleteRun() {
    const runId = $currentRunId;
    if (!runId || deleting) return;

    if (!confirm("Delete this run and all its results?")) return;

    deleting = true;
    try {
      await api.deleteRun(runId);
      runHistory.update((runs) => runs.filter((r) => r.id !== runId));
      currentRunWithResults.set(null);
      currentRunId.set(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to delete run");
    }
    deleting = false;
  }

  const selectedResult = $derived(
    $currentRunWithResults?.results.find((r) => r.id === selectedResultId) ?? null
  );
</script>

<div class="runs-view">
  {#if !$currentRunWithResults}
    <div class="empty-state">
      <p>No run selected</p>
      <p class="hint">Select a run from the sidebar or run tests from the Tests tab.</p>
    </div>
  {:else}
    <div class="run-header">
      <span class="run-date">{formatDate($currentRunWithResults.started_at)}</span>
      {#if !$currentRunWithResults.completed_at}
        <span class="status-badge running">
          <span class="mini-spinner"></span>
          Running
        </span>
      {:else}
        {@const summary = getRunSummary($currentRunWithResults.results)}
        <span class="summary">
          <span class="pass">{summary.passed} passed</span>
          <span class="fail">{summary.failed} failed</span>
        </span>
        <button
          class="delete-run-btn"
          onclick={deleteRun}
          disabled={deleting}
          title="Delete run"
        >
          {deleting ? "Deleting..." : "Delete"}
        </button>
      {/if}
    </div>

    <div class="layout">
      <section class="results">
        <ul class="results-list">
          {#each $currentRunWithResults.results as result}
            <li class:selected={selectedResultId === result.id}>
              <div class="result-row">
                <button
                  type="button"
                  class="result-select-btn"
                  onclick={() => (selectedResultId = result.id)}
                >
                  {#if result.status === "running"}
                    <span class="mini-spinner"></span>
                  {:else}
                    <span class="status {getStatusClass(result.status)}">
                      {result.status === "error" ? "ERR" : result.status === "cancelled" ? "SKIP" : result.status === "pass" ? "PASS" : "FAIL"}
                    </span>
                  {/if}
                  <span class="test-name">{result.test_name}</span>
                  {#if result.duration_ms}
                    <span class="duration">{result.duration_ms}ms</span>
                  {/if}
                </button>
                {#if result.status === "running"}
                  <button
                    type="button"
                    class="cancel-btn"
                    onclick={() => cancelTest(result.id)}
                    title="Cancel test"
                  >×</button>
                {/if}
              </div>
            </li>
          {/each}
        </ul>
      </section>

        <section class="detail">
          <h3>Detail View</h3>
          {#if !selectedResult}
            <p class="empty">Select a result to view details</p>
          {:else}
            {@const transcript = parseTranscript(selectedResult.transcript_json)}
            {@const metrics = parseMetrics(selectedResult.metrics_json)}
            {@const modelsUsed = parseModelsUsed(selectedResult.models_used)}

            <div class="result-detail">
              <div class="info-row">
                <span class="label">Test:</span>
                <span>{selectedResult.test_name}</span>
              </div>
              <div class="info-row">
                <span class="label">Status:</span>
                {#if selectedResult.status === "running"}
                  <span class="running">
                    <span class="mini-spinner"></span>
                    Running
                  </span>
                {:else}
                  <span class={getStatusClass(selectedResult.status)}>
                    {selectedResult.status === "error"
                      ? "Error"
                      : selectedResult.status === "cancelled"
                        ? "Cancelled"
                        : selectedResult.status === "pass"
                          ? "Passed"
                          : "Failed"}
                  </span>
                {/if}
              </div>
              {#if selectedResult.duration_ms}
                <div class="info-row">
                  <span class="label">Duration:</span>
                  <span>{selectedResult.duration_ms}ms</span>
                </div>
              {/if}
              <div class="info-row">
                <span class="label">End reason:</span>
                <span>{selectedResult.end_reason || "N/A"}</span>
              </div>

              {#if modelsUsed}
                <h4>Models Used</h4>
                <div class="models-used">
                  <div class="model-row">
                    <span class="label">Agent:</span>
                    <code>{modelsUsed.agent}</code>
                  </div>
                  <div class="model-row">
                    <span class="label">Simulator:</span>
                    <code>{modelsUsed.simulator}</code>
                  </div>
                  <div class="model-row">
                    <span class="label">Judge:</span>
                    <code>{modelsUsed.judge}</code>
                  </div>
                </div>
              {/if}

              {#if selectedResult.error_message}
                <div class="error-box">
                  <strong>Error:</strong>
                  <pre>{selectedResult.error_message}</pre>
                </div>
              {/if}

              <h4>Transcript</h4>
              <div class="transcript">
                {#each transcript as msg, i}
                  {@const prevNode = i > 0 ? transcript[i - 1].metadata?.node_id : null}
                  {@const currNode = msg.metadata?.node_id}
                  {#if currNode && currNode !== prevNode}
                    <div class="state-transition">
                      <span class="transition-arrow">→</span>
                      <span class="state-name">{currNode}</span>
                    </div>
                  {/if}
                  <div class="message {msg.role}">
                    <span class="role">{msg.role}</span>
                    <span class="content">{msg.content}</span>
                  </div>
                {:else}
                  {#if selectedResult.status !== "running"}
                    <p class="empty">No transcript</p>
                  {/if}
                {/each}
                {#if selectedResult.status === "running"}
                  {@const retry = $retryStatus.get(selectedResult.id)}
                  {#if retry}
                    <div class="retry-notice">
                      <span class="retry-icon">⏳</span>
                      <span class="retry-text">
                        Rate limited - retrying ({retry.attempt}/{retry.max_attempts})...
                        waiting {retry.retry_after.toFixed(1)}s
                      </span>
                    </div>
                  {:else}
                    {@const nextRole = transcript.length % 2 === 0 ? "user" : "assistant"}
                    <div class="message {nextRole} typing">
                      <span class="role">{nextRole}</span>
                      <span class="content typing-dots">
                        <span>.</span><span>.</span><span>.</span>
                      </span>
                    </div>
                  {/if}
                {/if}
              </div>

              {#if metrics.length > 0}
                <h4>Metrics</h4>
                <ul class="metrics">
                  {#each metrics as metric}
                    <li class={metric.passed ? "pass" : "fail"}>
                      <span class="metric-status">{metric.passed ? "PASS" : "FAIL"}</span>
                      <span class="metric-name">{metric.metric}</span>
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
    {/if}
</div>

<style>
  .runs-view {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .run-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .run-date {
    font-size: 0.9rem;
    color: var(--text-secondary);
  }

  .status-badge {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
  }

  .status-badge.running {
    background: #1e3a5f;
    color: #60a5fa;
  }

  .mini-spinner {
    width: 12px;
    height: 12px;
    border: 2px solid var(--border-color);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .in-progress {
    display: flex;
    align-items: center;
  }

  h3 {
    margin-top: 0;
    font-size: 1rem;
    color: var(--text-secondary);
  }

  h4 {
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin: 1rem 0 0.5rem 0;
  }

  .empty-state {
    background: var(--bg-secondary);
    padding: 2rem;
    border-radius: 8px;
    text-align: center;
  }

  .empty-state p {
    margin: 0;
    color: var(--text-secondary);
  }

  .empty-state .hint {
    margin-top: 0.5rem;
    font-size: 0.85rem;
    color: var(--text-muted);
  }

  .layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
    flex: 1;
    min-height: 0;
  }

  .results {
    background: var(--bg-secondary);
    padding: 1rem;
    border-radius: 8px;
    overflow-y: auto;
  }

  .summary {
    display: flex;
    gap: 0.5rem;
    font-size: 0.9rem;
  }

  .delete-run-btn {
    background: var(--danger-bg) !important;
    color: var(--danger-text) !important;
    padding: 0.25rem 0.5rem !important;
    font-size: 0.75rem !important;
    margin-left: auto;
  }

  .delete-run-btn:hover:not(:disabled) {
    background: var(--danger-bg-hover) !important;
  }

  .delete-run-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .results-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .results-list li {
    background: var(--bg-primary);
    border-radius: 4px;
    border: 1px solid transparent;
  }

  .results-list li:hover {
    border-color: var(--border-color);
  }

  .results-list li.selected {
    border-color: var(--accent);
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

  .result-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .status {
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.2rem 0.4rem;
    border-radius: 3px;
    background: var(--bg-hover);
  }

  .status.pass {
    background: var(--status-pass-bg);
    color: var(--color-pass);
  }

  .status.fail {
    background: var(--status-fail-bg);
    color: var(--color-fail);
  }

  .status.error {
    background: var(--status-error-bg);
    color: var(--color-error);
  }

  .status.cancelled {
    background: var(--bg-hover);
    color: var(--text-secondary);
  }

  .test-name {
    flex: 1;
  }

  .duration {
    color: var(--text-muted);
    font-size: 0.8rem;
  }

  .cancel-btn {
    background: var(--danger-bg) !important;
    color: var(--danger-text) !important;
    padding: 0.1rem 0.4rem !important;
    font-size: 0.9rem !important;
    line-height: 1;
    min-width: auto;
    border-radius: 3px;
  }

  .cancel-btn:hover {
    background: var(--danger-bg-hover) !important;
  }

  .empty {
    color: var(--text-muted);
    font-style: italic;
  }

  .detail {
    background: var(--bg-secondary);
    padding: 1rem;
    border-radius: 8px;
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
    color: var(--text-secondary);
    min-width: 80px;
  }

  .pass {
    color: #10b981;
  }

  .fail {
    color: #f87171;
  }

  .error {
    color: #fbbf24;
  }

  .cancelled {
    color: var(--text-secondary);
  }

  .running {
    color: #60a5fa;
    display: flex;
    align-items: center;
    gap: 0.5rem;
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
  }

  .state-transition {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    color: var(--text-muted);
    border-left: 2px solid #a855f7;
    background: rgba(168, 85, 247, 0.1);
    border-radius: 0 4px 4px 0;
  }

  .transition-arrow {
    color: #a855f7;
    font-weight: bold;
  }

  .state-name {
    font-family: monospace;
    color: #a855f7;
  }

  .message {
    padding: 0.5rem;
    border-radius: 4px;
    background: var(--bg-primary);
  }

  .message.user {
    border-left: 3px solid #3b82f6;
  }

  .message.assistant {
    border-left: 3px solid #10b981;
  }

  .role {
    font-size: 0.75rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    display: block;
    margin-bottom: 0.25rem;
  }

  .content {
    white-space: pre-wrap;
  }

  .typing-dots span {
    animation: blink 1.4s infinite both;
    font-weight: bold;
  }

  .typing-dots span:nth-child(2) {
    animation-delay: 0.2s;
  }

  .typing-dots span:nth-child(3) {
    animation-delay: 0.4s;
  }

  .retry-notice {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem;
    background: #78350f;
    border-radius: 4px;
    border-left: 3px solid #fbbf24;
    color: #fef3c7;
  }

  .retry-icon {
    font-size: 1.2rem;
  }

  .retry-text {
    font-size: 0.9rem;
  }

  @keyframes blink {
    0%, 80%, 100% { opacity: 0.2; }
    40% { opacity: 1; }
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
    background: var(--bg-primary);
    border-radius: 4px;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: flex-start;
  }

  .metrics li.pass {
    border-left: 3px solid #10b981;
  }

  .metrics li.fail {
    border-left: 3px solid #f87171;
  }

  .metric-status {
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.15rem 0.3rem;
    border-radius: 3px;
    background: var(--bg-hover);
  }

  .metrics li.pass .metric-status {
    background: var(--status-pass-bg);
    color: var(--color-pass);
  }

  .metrics li.fail .metric-status {
    background: var(--status-fail-bg);
    color: var(--color-fail);
  }

  .metric-name {
    font-weight: 500;
    flex: 1;
  }

  .metric-reason {
    width: 100%;
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .models-used {
    background: var(--bg-primary);
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
    background: var(--bg-hover);
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-size: 0.8rem;
  }

  @media (max-width: 768px) {
    .run-header {
      grid-template-columns: 1fr;
      gap: 0.5rem;
    }
  }
</style>
