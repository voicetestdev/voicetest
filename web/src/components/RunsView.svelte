<script lang="ts">
  import { api } from "../lib/api";
  import {
    currentRunWithResults,
    currentRunId,
    currentAgentId,
    runHistory,
    cancelTest,
    retryStatus,
    loadRun,
    startRun,
    currentView,
  } from "../lib/stores";
  import type {
    RunResultRecord,
    Message,
    MetricResult,
    ModelsUsed,
    DiagnoseResponse,
    ApplyFixResponse,
    PromptChange,
    AutoFixStopCondition,
  } from "../lib/types";

  let audioEvalLoading = $state<string | null>(null);

  // Diagnosis state
  let diagnosing = $state(false);
  let diagnosisResult = $state<DiagnoseResponse | null>(null);
  let applyingFix = $state(false);
  let fixResult = $state<ApplyFixResponse | null>(null);
  let savingFix = $state(false);
  let currentChanges = $state<PromptChange[]>([]);
  let iterationCount = $state(0);
  let diagnosisError = $state<string | null>(null);
  let diagnosisModel = $state("");

  // Auto-fix state
  let autoFixRunning = $state(false);
  let autoFixCancelled = $state(false);
  let autoFixMaxIterations = $state(3);
  let autoFixStopCondition = $state<AutoFixStopCondition>("improve");
  let autoFixPhase = $state("");
  let autoFixIteration = $state(0);
  let previousScores = $state<Record<string, number>>({});

  // Reset diagnosis state when selected result changes
  $effect(() => {
    selectedResultId;
    diagnosisResult = null;
    fixResult = null;
    currentChanges = [];
    iterationCount = 0;
    diagnosisError = null;
    autoFixRunning = false;
    autoFixCancelled = false;
    autoFixPhase = "";
    autoFixIteration = 0;
    previousScores = {};
  });

  async function runDiagnosis(resultId: string) {
    diagnosing = true;
    diagnosisError = null;
    try {
      const model = diagnosisModel.trim() || undefined;
      diagnosisResult = await api.diagnoseResult(resultId, model);
      currentChanges = diagnosisResult.fix.changes;
    } catch (e) {
      diagnosisError = e instanceof Error ? e.message : "Diagnosis failed";
    }
    diagnosing = false;
  }

  async function applyAndTest(resultId: string) {
    applyingFix = true;
    iterationCount++;
    try {
      fixResult = await api.applyFix(resultId, currentChanges, iterationCount);
    } catch (e) {
      diagnosisError = e instanceof Error ? e.message : "Apply fix failed";
    }
    applyingFix = false;
  }

  async function tryAgain(resultId: string) {
    if (!diagnosisResult || !fixResult) return;
    applyingFix = true;
    diagnosisError = null;
    try {
      const newMetrics = fixResult.metric_results;
      previousScores = { ...fixResult.new_scores };
      const model = diagnosisModel.trim() || undefined;
      const revised = await api.reviseFix(
        resultId,
        diagnosisResult.diagnosis,
        currentChanges,
        newMetrics,
        model,
      );
      currentChanges = revised.changes;
      fixResult = null;
      // Show the revised suggestion for review
      diagnosisResult = {
        ...diagnosisResult,
        fix: revised,
      };
    } catch (e) {
      diagnosisError = e instanceof Error ? e.message : "Revision failed";
    }
    applyingFix = false;
  }

  async function saveChanges() {
    const agentId = $currentAgentId;
    if (!agentId) return;
    savingFix = true;
    try {
      await api.saveFix(agentId, currentChanges);
      diagnosisResult = null;
      fixResult = null;
      currentChanges = [];
      iterationCount = 0;
    } catch (e) {
      diagnosisError = e instanceof Error ? e.message : "Save failed";
    }
    savingFix = false;
  }

  function dismissDiagnosis() {
    diagnosisResult = null;
    fixResult = null;
    currentChanges = [];
    iterationCount = 0;
    diagnosisError = null;
    autoFixRunning = false;
    autoFixCancelled = false;
    previousScores = {};
  }

  function cancelAutoFix() {
    autoFixCancelled = true;
  }

  async function runAutoFix(resultId: string) {
    autoFixRunning = true;
    autoFixCancelled = false;
    autoFixIteration = 0;
    diagnosisError = null;
    previousScores = {};
    const model = diagnosisModel.trim() || undefined;

    try {
      // Step 1: Diagnose
      autoFixPhase = "Diagnosing failure...";
      diagnosisResult = await api.diagnoseResult(resultId, model);
      currentChanges = diagnosisResult.fix.changes;

      // Step 2: Iterate
      for (let i = 0; i < autoFixMaxIterations; i++) {
        if (autoFixCancelled) {
          autoFixPhase = "Cancelled";
          break;
        }

        autoFixIteration = i + 1;
        iterationCount = i + 1;
        autoFixPhase = `Applying fix & testing (iteration ${i + 1}/${autoFixMaxIterations})...`;

        fixResult = await api.applyFix(resultId, currentChanges, i + 1);

        // Check stop condition
        const stopOnImprove = autoFixStopCondition === "improve" && fixResult.improved;
        const stopOnPass = autoFixStopCondition === "pass" && fixResult.test_passed;
        if (stopOnPass || fixResult.test_passed) {
          autoFixPhase = "All metrics pass";
          break;
        }
        if (stopOnImprove) {
          autoFixPhase = "Scores improved";
          break;
        }

        // If not last iteration, revise
        if (i < autoFixMaxIterations - 1 && !autoFixCancelled) {
          autoFixPhase = `Revising fix (iteration ${i + 1}/${autoFixMaxIterations})...`;
          previousScores = { ...fixResult.new_scores };
          const revised = await api.reviseFix(
            resultId,
            diagnosisResult.diagnosis,
            currentChanges,
            fixResult.metric_results,
            model,
          );
          currentChanges = revised.changes;
          diagnosisResult = { ...diagnosisResult, fix: revised };
          fixResult = null;
        }
      }
    } catch (e) {
      diagnosisError = e instanceof Error ? e.message : "Auto-fix failed";
    }
    autoFixRunning = false;
  }

  function getLocationLabel(locationType: string): string {
    switch (locationType) {
      case "general_prompt": return "General Prompt";
      case "node_prompt": return "Node Prompt";
      case "transition": return "Transition";
      case "missing_transition": return "Missing Transition";
      default: return locationType;
    }
  }

  function hasAudioEval(result: RunResultRecord): boolean {
    const transcript = parseTranscript(result.transcript_json);
    return transcript.some((m) => m.role === "assistant" && m.metadata?.heard);
  }

  async function runAudioEval(resultId: string) {
    audioEvalLoading = resultId;
    try {
      const updated = await api.audioEvalResult(resultId);
      // Update the result in the store
      currentRunWithResults.update((run) => {
        if (!run) return run;
        return {
          ...run,
          results: run.results.map((r) =>
            r.id === resultId ? { ...r, ...updated } : r
          ),
        };
      });
    } catch (e) {
      alert(e instanceof Error ? e.message : "Audio evaluation failed");
    }
    audioEvalLoading = null;
  }

  function parseAudioMetrics(json: string | MetricResult[] | null): MetricResult[] {
    if (!json) return [];
    if (Array.isArray(json)) return json;
    try {
      return JSON.parse(json);
    } catch {
      return [];
    }
  }

  function diffWords(original: string, heard: string): string {
    const origWords = original.split(/\s+/);
    const heardWords = heard.split(/\s+/);
    const result: string[] = [];

    const m = origWords.length;
    const n = heardWords.length;

    // Build LCS table
    const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
    for (let i = 1; i <= m; i++) {
      for (let j = 1; j <= n; j++) {
        if (origWords[i - 1].toLowerCase() === heardWords[j - 1].toLowerCase()) {
          dp[i][j] = dp[i - 1][j - 1] + 1;
        } else {
          dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
      }
    }

    // Backtrack to produce diff
    let i = m, j = n;
    const parts: { type: "same" | "del" | "ins"; text: string }[] = [];
    while (i > 0 || j > 0) {
      if (i > 0 && j > 0 && origWords[i - 1].toLowerCase() === heardWords[j - 1].toLowerCase()) {
        parts.unshift({ type: "same", text: origWords[i - 1] });
        i--; j--;
      } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
        parts.unshift({ type: "ins", text: heardWords[j - 1] });
        j--;
      } else {
        parts.unshift({ type: "del", text: origWords[i - 1] });
        i--;
      }
    }

    for (const part of parts) {
      const escaped = part.text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      if (part.type === "del") {
        result.push(`<del>${escaped}</del>`);
      } else if (part.type === "ins") {
        result.push(`<ins>${escaped}</ins>`);
      } else {
        result.push(escaped);
      }
    }

    return result.join(" ");
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

  async function selectRun(runId: string) {
    await loadRun(runId);
  }

  let selectedResultId = $state<string | null>(null);
  let deleting = $state(false);
  let rerunOpen = $state(false);
  let rerunDropdownEl: HTMLElement;
  let detailContainer: HTMLElement;
  let prevMessageCount = 0;

  // Auto-select: running test takes priority, otherwise first result
  $effect(() => {
    const results = $currentRunWithResults?.results ?? [];
    if (results.length === 0) return;

    const runningResult = results.find((r) => r.status === "running");
    if (runningResult && selectedResultId !== runningResult.id) {
      // Running test takes priority
      const currentSelection = results.find((r) => r.id === selectedResultId);
      if (!currentSelection || currentSelection.status !== "running") {
        selectedResultId = runningResult.id;
      }
    } else if (!selectedResultId || !results.find((r) => r.id === selectedResultId)) {
      // Nothing selected or selection no longer exists - select first result
      selectedResultId = results[0].id;
    }
  });


  function parseTranscript(json: string | Message[] | null): Message[] {
    if (!json) return [];
    if (Array.isArray(json)) return json;
    try {
      return JSON.parse(json);
    } catch {
      return [];
    }
  }

  function parseMetrics(json: string | MetricResult[] | null): MetricResult[] {
    if (!json) return [];
    if (Array.isArray(json)) return json;
    try {
      return JSON.parse(json);
    } catch {
      return [];
    }
  }

  function parseModelsUsed(json: string | ModelsUsed | null): ModelsUsed | null {
    if (!json) return null;
    if (typeof json === "object") return json;
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

  function getRunSummary(results: RunResultRecord[]): { passed: number; failed: number; errors: number; total: number } {
    const passed = results.filter((r) => r.status === "pass").length;
    const failed = results.filter((r) => r.status === "fail").length;
    const errors = results.filter((r) => r.status === "error").length;
    return { passed, failed, errors, total: results.length };
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

  function handleClickOutside(event: MouseEvent) {
    if (rerunOpen && rerunDropdownEl && !rerunDropdownEl.contains(event.target as Node)) {
      rerunOpen = false;
    }
  }

  const rerunnableResults = $derived(
    ($currentRunWithResults?.results ?? []).filter((r) => r.test_case_id)
  );

  const failedResults = $derived(
    rerunnableResults.filter((r) => r.status === "fail" || r.status === "error")
  );

  const selectedRerunResult = $derived(
    rerunnableResults.find((r) => r.id === selectedResultId) ?? null
  );

  async function rerunTests(testIds: string[]) {
    const agentId = $currentAgentId;
    if (!agentId || testIds.length === 0) return;
    rerunOpen = false;
    currentView.set("runs");
    await startRun(agentId, testIds);
  }

  function rerunAll() {
    const ids = rerunnableResults.map((r) => r.test_case_id!);
    rerunTests(ids);
  }

  function rerunFailed() {
    const ids = failedResults.map((r) => r.test_case_id!);
    rerunTests(ids);
  }

  function rerunSelected() {
    if (!selectedRerunResult?.test_case_id) return;
    rerunTests([selectedRerunResult.test_case_id]);
  }

  const selectedResult = $derived(
    $currentRunWithResults?.results.find((r) => r.id === selectedResultId) ?? null
  );

  // Auto-scroll detail view to bottom only when NEW messages arrive
  $effect(() => {
    const result = selectedResult;
    if (result?.transcript_json && detailContainer) {
      const messages = parseTranscript(result.transcript_json);
      const messageCount = messages.length;

      // Only scroll if message count increased (new message arrived)
      if (messageCount > prevMessageCount) {
        prevMessageCount = messageCount;
        requestAnimationFrame(() => {
          detailContainer.scrollTop = detailContainer.scrollHeight;
        });
      }
    }
  });

  // Reset message count when switching results
  $effect(() => {
    selectedResultId;
    prevMessageCount = 0;
  });
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<svelte:window onclick={handleClickOutside} />

<div class="runs-view">
  {#if !$currentRunWithResults && $runHistory.length === 0}
    <div class="empty-state">
      <p>No runs yet</p>
      <p class="hint">Run tests from the Tests tab to see results here.</p>
    </div>
  {:else}
    <div class="run-header">
      {#if $runHistory.length > 0}
        <select
          class="run-select"
          value={$currentRunId || ""}
          onchange={(e) => selectRun(e.currentTarget.value)}
        >
          {#each $runHistory as run}
            <option value={run.id}>
              {formatRelativeTime(run.started_at)}{!run.completed_at ? " (running)" : ""}
            </option>
          {/each}
        </select>
      {/if}
      {#if $currentRunWithResults}
        {#if !$currentRunWithResults.completed_at}
          <span class="status-badge running">
            <span class="mini-spinner"></span>
            Running
          </span>
        {:else}
          {@const summary = getRunSummary($currentRunWithResults.results)}
          <span class="summary">
            <span class="pass">{summary.passed} passed</span>
            {#if summary.failed > 0}
              <span class="fail">{summary.failed} failed</span>
            {/if}
            {#if summary.errors > 0}
              <span class="error">{summary.errors} errors</span>
            {/if}
          </span>
        {/if}
        {#if $currentRunWithResults.completed_at && rerunnableResults.length > 0}
          <div class="rerun-dropdown" bind:this={rerunDropdownEl}>
            <button
              class="rerun-btn"
              onclick={() => (rerunOpen = !rerunOpen)}
              title="Re-run tests"
            >
              Re-run
              <span class="caret"></span>
            </button>
            {#if rerunOpen}
              <ul class="rerun-menu">
                <li>
                  <button onclick={rerunAll}>
                    Re-run all tests ({rerunnableResults.length})
                  </button>
                </li>
                {#if failedResults.length > 0}
                  <li>
                    <button onclick={rerunFailed}>
                      Re-run failed tests ({failedResults.length})
                    </button>
                  </li>
                {/if}
                {#if selectedRerunResult}
                  <li>
                    <button onclick={rerunSelected}>
                      Re-run {selectedRerunResult.test_name.length > 30
                        ? selectedRerunResult.test_name.slice(0, 30) + "..."
                        : selectedRerunResult.test_name}
                    </button>
                  </li>
                {/if}
              </ul>
            {/if}
          </div>
        {/if}
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

    {#if $currentRunWithResults}
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

        <section class="detail" bind:this={detailContainer}>
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

              {#if selectedResult.status !== "running" && selectedResult.test_case_id && !hasAudioEval(selectedResult)}
                <button
                  class="audio-eval-btn"
                  onclick={() => runAudioEval(selectedResult.id)}
                  disabled={audioEvalLoading === selectedResult.id}
                >
                  {audioEvalLoading === selectedResult.id ? "Running audio eval..." : "Run audio eval"}
                </button>
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
                    {#if msg.metadata?.heard && msg.role === "assistant"}
                      <div class="audio-diff">
                        {@html diffWords(msg.content, msg.metadata.heard as string)}
                      </div>
                    {:else}
                      <span class="content">{msg.content}</span>
                    {/if}
                  </div>
                {:else}
                  {#if selectedResult.status !== "running"}
                    <p class="empty">No transcript</p>
                  {/if}
                {/each}
                {#if selectedResult.status === "running"}
                  {@const retry = $retryStatus[selectedResult.id]}
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
                {:else if selectedResult.status === "error"}
                  {@const retry = $retryStatus[selectedResult.id]}
                  {#if retry}
                    <div class="retry-notice failed">
                      <span class="retry-icon">⚠️</span>
                      <span class="retry-text">
                        Failed after {retry.attempt} retry attempts ({retry.error_type})
                      </span>
                    </div>
                  {/if}
                {/if}
              </div>

              {#if metrics.length > 0}
                <h4>Metrics</h4>
                <ul class="metrics">
                  {#each metrics as metric}
                    {@const clampedScore = metric.score !== undefined
                      ? Math.min(1, Math.max(0, metric.score))
                      : undefined}
                    {@const scoreColor = clampedScore !== undefined
                      ? clampedScore >= 0.7 ? "green"
                        : clampedScore >= 0.4 ? "yellow"
                        : "red"
                      : metric.passed ? "green" : "red"}
                    <li class={metric.passed ? "pass" : "fail"}>
                      <span class="metric-status">{metric.passed ? "PASS" : "FAIL"}</span>
                      {#if clampedScore !== undefined}
                        <span class="metric-score {scoreColor}">
                          {(clampedScore * 100).toFixed(0)}%
                        </span>
                      {/if}
                      <span class="metric-name">{metric.metric}</span>
                      {#if metric.threshold !== undefined}
                        {@const clampedThreshold = Math.min(1, Math.max(0, metric.threshold))}
                        <span class="metric-threshold">threshold: {(clampedThreshold * 100).toFixed(0)}%</span>
                      {/if}
                      {#if metric.reasoning}
                        <span class="metric-reason">{metric.reasoning}</span>
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/if}

              {#if parseAudioMetrics(selectedResult.audio_metrics_json).length > 0}
                <h4>Audio Evaluation</h4>
                <ul class="metrics">
                  {#each parseAudioMetrics(selectedResult.audio_metrics_json) as metric}
                    {@const clampedScore = metric.score !== undefined
                      ? Math.min(1, Math.max(0, metric.score))
                      : undefined}
                    {@const scoreColor = clampedScore !== undefined
                      ? clampedScore >= 0.7 ? "green"
                        : clampedScore >= 0.4 ? "yellow"
                        : "red"
                      : metric.passed ? "green" : "red"}
                    <li class={metric.passed ? "pass" : "fail"}>
                      <span class="metric-status">{metric.passed ? "PASS" : "FAIL"}</span>
                      {#if clampedScore !== undefined}
                        <span class="metric-score {scoreColor}">
                          {(clampedScore * 100).toFixed(0)}%
                        </span>
                      {/if}
                      <span class="metric-name">{metric.metric}</span>
                      {#if metric.threshold !== undefined}
                        {@const clampedThreshold = Math.min(1, Math.max(0, metric.threshold))}
                        <span class="metric-threshold">threshold: {(clampedThreshold * 100).toFixed(0)}%</span>
                      {/if}
                      {#if metric.reasoning}
                        <span class="metric-reason">{metric.reasoning}</span>
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/if}

              {#if selectedResult.status === "fail" && selectedResult.test_case_id && !diagnosisResult && !diagnosing && !autoFixRunning}
                <div class="diagnosis-controls">
                  <input
                    type="text"
                    class="model-input"
                    placeholder="Judge model (default from settings)"
                    bind:value={diagnosisModel}
                  />
                  <div class="diagnosis-buttons">
                    <button
                      class="diagnose-btn"
                      onclick={() => runDiagnosis(selectedResult.id)}
                      disabled={diagnosing}
                    >
                      Diagnose
                    </button>
                    <button
                      class="auto-fix-btn"
                      onclick={() => runAutoFix(selectedResult.id)}
                    >
                      Auto Fix
                    </button>
                  </div>
                  <div class="auto-fix-options">
                    <label class="auto-fix-label">
                      Stop:
                      <select bind:value={autoFixStopCondition}>
                        <option value="improve">On improvement</option>
                        <option value="pass">When all pass</option>
                      </select>
                    </label>
                    <label class="auto-fix-label">
                      Max:
                      <input
                        type="number"
                        min="1"
                        max="10"
                        bind:value={autoFixMaxIterations}
                        class="iterations-input"
                      />
                    </label>
                  </div>
                </div>
              {/if}

              {#if diagnosing}
                <div class="diagnosis-loading">
                  <span class="mini-spinner"></span>
                  Analyzing failure...
                </div>
              {/if}

              {#if autoFixRunning}
                <div class="auto-fix-progress">
                  <div class="auto-fix-status">
                    <span class="mini-spinner"></span>
                    <span>{autoFixPhase}</span>
                    <span class="iteration-badge">{autoFixIteration}/{autoFixMaxIterations}</span>
                  </div>
                  {#if fixResult}
                    <table class="score-comparison compact">
                      <thead>
                        <tr>
                          <th>Metric</th>
                          <th>Original</th>
                          {#if Object.keys(previousScores).length > 0}
                            <th>Previous</th>
                          {/if}
                          <th>Current</th>
                          <th>vs Original</th>
                          {#if Object.keys(previousScores).length > 0}
                            <th>vs Previous</th>
                          {/if}
                        </tr>
                      </thead>
                      <tbody>
                        {#each Object.keys(fixResult.new_scores) as metric}
                          {@const orig = fixResult.original_scores[metric] ?? 0}
                          {@const prev = previousScores[metric] ?? orig}
                          {@const current = fixResult.new_scores[metric] ?? 0}
                          {@const deltaOrig = current - orig}
                          {@const deltaPrev = current - prev}
                          <tr>
                            <td class="metric-cell">{metric}</td>
                            <td>{(orig * 100).toFixed(0)}%</td>
                            {#if Object.keys(previousScores).length > 0}
                              <td>{(prev * 100).toFixed(0)}%</td>
                            {/if}
                            <td>{(current * 100).toFixed(0)}%</td>
                            <td class={deltaOrig > 0 ? "delta-positive" : deltaOrig < 0 ? "delta-negative" : "delta-neutral"}>
                              {deltaOrig > 0 ? "+" : ""}{(deltaOrig * 100).toFixed(0)}%
                            </td>
                            {#if Object.keys(previousScores).length > 0}
                              <td class={deltaPrev > 0 ? "delta-positive" : deltaPrev < 0 ? "delta-negative" : "delta-neutral"}>
                                {deltaPrev > 0 ? "+" : ""}{(deltaPrev * 100).toFixed(0)}%
                              </td>
                            {/if}
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  {/if}
                  <button class="cancel-auto-fix-btn" onclick={cancelAutoFix}>
                    Cancel
                  </button>
                </div>
              {/if}

              {#if diagnosisError}
                <div class="error-box">
                  <strong>Diagnosis Error:</strong>
                  <pre>{diagnosisError}</pre>
                </div>
              {/if}

              {#if diagnosisResult}
                <div class="diagnosis-panel">
                  <h4>Diagnosis</h4>

                  <div class="diagnosis-section">
                    <span class="diagnosis-label">Root Cause</span>
                    <p class="diagnosis-text">{diagnosisResult.diagnosis.root_cause}</p>
                  </div>

                  {#if diagnosisResult.diagnosis.fault_locations.length > 0}
                    <div class="diagnosis-section">
                      <span class="diagnosis-label">Fault Locations</span>
                      <ul class="fault-locations">
                        {#each diagnosisResult.diagnosis.fault_locations as loc}
                          <li>
                            <span class="location-badge {loc.location_type}">{getLocationLabel(loc.location_type)}</span>
                            {#if loc.node_id}
                              <code class="node-ref">{loc.node_id}</code>
                            {/if}
                            <pre class="relevant-text">{loc.relevant_text}</pre>
                            <span class="fault-explanation">{loc.explanation}</span>
                          </li>
                        {/each}
                      </ul>
                    </div>
                  {/if}

                  {#if diagnosisResult.diagnosis.transcript_evidence}
                    <div class="diagnosis-section">
                      <span class="diagnosis-label">Evidence</span>
                      <blockquote class="transcript-evidence">{diagnosisResult.diagnosis.transcript_evidence}</blockquote>
                    </div>
                  {/if}

                  <h4>Suggested Fix</h4>
                  <div class="fix-summary">
                    <p>{diagnosisResult.fix.summary}</p>
                    <span class="confidence-badge">
                      {(diagnosisResult.fix.confidence * 100).toFixed(0)}% confidence
                    </span>
                  </div>

                  {#if currentChanges.length > 0}
                    <ul class="proposed-changes">
                      {#each currentChanges as change, i}
                        <li>
                          <span class="location-badge {change.location_type}">{getLocationLabel(change.location_type)}</span>
                          {#if change.node_id}
                            <code class="node-ref">{change.node_id}</code>
                          {/if}
                          <div class="change-diff">
                            <del>{change.original_text}</del>
                            <textarea
                              class="proposed-text-edit"
                              bind:value={currentChanges[i].proposed_text}
                              rows={Math.max(3, change.proposed_text.split('\n').length)}
                            ></textarea>
                          </div>
                          <span class="change-rationale">{change.rationale}</span>
                        </li>
                      {/each}
                    </ul>
                  {/if}

                  {#if !fixResult}
                    <div class="diagnosis-actions">
                      <button
                        class="apply-btn"
                        onclick={() => applyAndTest(selectedResult.id)}
                        disabled={applyingFix}
                      >
                        {applyingFix ? "Applying..." : "Apply & Test"}
                      </button>
                      <button class="dismiss-btn" onclick={dismissDiagnosis}>
                        Dismiss
                      </button>
                    </div>
                  {/if}
                </div>
              {/if}

              {#if applyingFix && !fixResult}
                <div class="diagnosis-loading">
                  <span class="mini-spinner"></span>
                  Applying fix and re-running test...
                </div>
              {/if}

              {#if fixResult && !autoFixRunning}
                <div class="fix-result-panel">
                  <h4>Fix Result (Iteration {fixResult.iteration})</h4>

                  <table class="score-comparison">
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>Original</th>
                        {#if Object.keys(previousScores).length > 0}
                          <th>Previous</th>
                        {/if}
                        <th>After Fix</th>
                        <th>vs Original</th>
                        {#if Object.keys(previousScores).length > 0}
                          <th>vs Previous</th>
                        {/if}
                      </tr>
                    </thead>
                    <tbody>
                      {#each Object.keys(fixResult.new_scores) as metric}
                        {@const orig = fixResult.original_scores[metric] ?? 0}
                        {@const prev = previousScores[metric] ?? orig}
                        {@const updated = fixResult.new_scores[metric] ?? 0}
                        {@const deltaOrig = updated - orig}
                        {@const deltaPrev = updated - prev}
                        <tr>
                          <td class="metric-cell">{metric}</td>
                          <td>{(orig * 100).toFixed(0)}%</td>
                          {#if Object.keys(previousScores).length > 0}
                            <td>{(prev * 100).toFixed(0)}%</td>
                          {/if}
                          <td>{(updated * 100).toFixed(0)}%</td>
                          <td class={deltaOrig > 0 ? "delta-positive" : deltaOrig < 0 ? "delta-negative" : "delta-neutral"}>
                            {deltaOrig > 0 ? "+" : ""}{(deltaOrig * 100).toFixed(0)}%
                          </td>
                          {#if Object.keys(previousScores).length > 0}
                            <td class={deltaPrev > 0 ? "delta-positive" : deltaPrev < 0 ? "delta-negative" : "delta-neutral"}>
                              {deltaPrev > 0 ? "+" : ""}{(deltaPrev * 100).toFixed(0)}%
                            </td>
                          {/if}
                        </tr>
                      {/each}
                    </tbody>
                  </table>

                  {#if fixResult.test_passed}
                    <div class="fix-status pass">All metrics pass</div>
                  {:else if fixResult.improved}
                    <div class="fix-status improved">Improved (not all passing yet)</div>
                  {:else}
                    <div class="fix-status no-improvement">No improvement</div>
                  {/if}

                  <div class="fix-actions">
                    {#if fixResult.test_passed || fixResult.improved}
                      <button
                        class="save-btn"
                        onclick={saveChanges}
                        disabled={savingFix}
                      >
                        {savingFix ? "Saving..." : "Save Changes"}
                      </button>
                    {/if}
                    {#if !fixResult.test_passed}
                      <button
                        class="retry-btn"
                        onclick={() => tryAgain(selectedResult.id)}
                        disabled={applyingFix}
                      >
                        Try Again
                      </button>
                    {/if}
                    <button class="dismiss-btn" onclick={dismissDiagnosis}>
                      Discard
                    </button>
                  </div>
                </div>
              {/if}
            </div>
          {/if}
        </section>
      </div>
    {/if}
  {/if}
</div>

<style>
  .runs-view {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .run-select {
    min-width: 160px;
    padding: var(--space-2) var(--space-3);
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .run-select:focus {
    outline: none;
    border-color: var(--accent-blue);
    box-shadow: 0 0 0 3px rgba(31, 111, 235, 0.3);
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
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    text-align: center;
  }

  .empty-state p {
    margin: 0;
    color: var(--text-secondary);
  }

  .empty-state .hint {
    margin-top: 0.5rem;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .layout {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: var(--space-4);
    flex: 1;
    min-height: 0;
  }

  .results {
    background: var(--bg-secondary);
    padding: var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    overflow-y: auto;
  }

  .summary {
    display: flex;
    gap: 0.5rem;
    font-size: 0.9rem;
  }

  .rerun-dropdown {
    position: relative;
    margin-left: auto;
  }

  .rerun-btn {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.6rem !important;
    font-size: 0.75rem !important;
    background: var(--status-pass-bg) !important;
    color: var(--color-pass) !important;
    border: 1px solid rgba(63, 185, 80, 0.3) !important;
    border-radius: var(--radius-md);
    cursor: pointer;
    font-weight: 600;
  }

  .rerun-btn:hover {
    background: rgba(63, 185, 80, 0.25) !important;
  }

  .caret {
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid currentColor;
  }

  .rerun-menu {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    z-index: 100;
    min-width: 220px;
    list-style: none;
    margin: 0;
    padding: 0.25rem 0;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }

  .rerun-menu li button {
    display: block;
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: transparent !important;
    border: none !important;
    color: var(--text-primary);
    font-size: 0.8rem;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
  }

  .rerun-menu li button:hover {
    background: var(--bg-hover) !important;
  }

  .delete-run-btn {
    background: var(--danger-bg) !important;
    color: var(--danger-text) !important;
    padding: 0.25rem 0.5rem !important;
    font-size: 0.75rem !important;
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
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    transition: background 80ms ease-out;
  }

  .results-list li:hover {
    background: var(--bg-hover);
  }

  .results-list li.selected {
    border-color: var(--accent-blue);
    background: var(--bg-hover);
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
    font-size: var(--text-xs);
    font-weight: 600;
    padding: 0.15rem 0.4rem;
    border-radius: 9999px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
  }

  .status.pass {
    background: var(--status-pass-bg);
    color: var(--color-pass);
    border-color: rgba(63, 185, 80, 0.3);
  }

  .status.fail {
    background: var(--status-fail-bg);
    color: var(--color-fail);
    border-color: rgba(248, 81, 73, 0.3);
  }

  .status.error {
    background: var(--status-error-bg);
    color: var(--color-error);
    border-color: rgba(210, 153, 34, 0.3);
  }

  .status.cancelled {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    border-color: var(--border-color);
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
    padding: var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    overflow-y: auto;
    scroll-behavior: smooth;
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
    padding: var(--space-3);
    border-radius: var(--radius-md);
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
  }

  .message.user {
    border-left: 3px solid var(--accent-blue);
  }

  .message.assistant {
    border-left: 3px solid var(--color-pass);
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

  .retry-notice.failed {
    background: #7f1d1d;
    border-left-color: #f87171;
    color: #fecaca;
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

  .metric-score {
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.15rem 0.4rem;
    border-radius: 3px;
  }

  .metric-score.green {
    background: #065f46;
    color: #34d399;
  }

  .metric-score.yellow {
    background: #78350f;
    color: #fbbf24;
  }

  .metric-score.red {
    background: #7f1d1d;
    color: #f87171;
  }

  .metric-threshold {
    font-size: 0.7rem;
    color: var(--text-muted);
    font-style: italic;
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

  @media (max-width: 900px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: auto 1fr;
    }

    .results {
      max-height: 200px;
    }
  }

  .audio-eval-btn {
    margin-top: 0.5rem;
    padding: 0.35rem 0.75rem !important;
    font-size: 0.8rem !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    color: var(--text-secondary) !important;
    cursor: pointer;
  }

  .audio-eval-btn:hover:not(:disabled) {
    background: var(--bg-hover) !important;
    color: var(--text-primary) !important;
  }

  .audio-eval-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .audio-diff {
    white-space: pre-wrap;
  }

  .audio-diff :global(del) {
    background: rgba(248, 113, 113, 0.2);
    color: var(--danger-text, #f87171);
    text-decoration: line-through;
  }

  .audio-diff :global(ins) {
    background: rgba(34, 197, 94, 0.2);
    color: #22c55e;
    text-decoration: none;
  }

  @media (max-width: 768px) {
    .run-header {
      flex-wrap: wrap;
      gap: var(--space-2);
    }
  }

  .diagnosis-controls {
    margin-top: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .model-input {
    padding: 0.35rem 0.5rem;
    font-size: 0.8rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    width: 100%;
  }

  .model-input::placeholder {
    color: var(--text-muted);
  }

  .model-input:focus {
    outline: none;
    border-color: var(--accent-blue);
  }

  .diagnosis-buttons {
    display: flex;
    gap: 0.5rem;
  }

  .diagnose-btn {
    padding: 0.4rem 0.85rem !important;
    font-size: 0.8rem !important;
    background: #1e3a5f !important;
    border: 1px solid rgba(96, 165, 250, 0.3) !important;
    color: #60a5fa !important;
    cursor: pointer;
    font-weight: 600;
  }

  .diagnose-btn:hover:not(:disabled) {
    background: rgba(96, 165, 250, 0.2) !important;
  }

  .auto-fix-btn {
    padding: 0.4rem 0.85rem !important;
    font-size: 0.8rem !important;
    background: #4c1d95 !important;
    border: 1px solid rgba(167, 139, 250, 0.3) !important;
    color: #a78bfa !important;
    cursor: pointer;
    font-weight: 600;
  }

  .auto-fix-btn:hover {
    background: rgba(167, 139, 250, 0.2) !important;
  }

  .auto-fix-options {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  .auto-fix-label {
    font-size: 0.75rem;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .auto-fix-label select {
    padding: 0.2rem 0.4rem;
    font-size: 0.75rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
  }

  .iterations-input {
    width: 3rem;
    padding: 0.2rem 0.4rem;
    font-size: 0.75rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    text-align: center;
  }

  .auto-fix-progress {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: #1a1040;
    border: 1px solid rgba(167, 139, 250, 0.3);
    border-radius: var(--radius-md);
  }

  .auto-fix-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #a78bfa;
    font-size: 0.85rem;
    margin-bottom: 0.5rem;
  }

  .iteration-badge {
    font-size: 0.7rem;
    padding: 0.1rem 0.4rem;
    background: #4c1d95;
    border-radius: 3px;
    font-weight: 600;
  }

  .score-comparison.compact {
    font-size: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .cancel-auto-fix-btn {
    padding: 0.3rem 0.6rem !important;
    font-size: 0.75rem !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    color: var(--text-secondary) !important;
    cursor: pointer;
  }

  .cancel-auto-fix-btn:hover {
    background: var(--bg-hover) !important;
    color: #f87171 !important;
  }

  .diagnosis-loading {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem;
    margin-top: 0.75rem;
    background: #1e3a5f;
    border-radius: 4px;
    color: #60a5fa;
    font-size: 0.85rem;
  }

  .diagnosis-panel {
    margin-top: 1rem;
    padding: 0.75rem;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
  }

  .diagnosis-panel h4 {
    margin-top: 0.75rem;
  }

  .diagnosis-panel h4:first-child {
    margin-top: 0;
  }

  .diagnosis-section {
    margin-bottom: 0.75rem;
  }

  .diagnosis-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    display: block;
    margin-bottom: 0.25rem;
  }

  .diagnosis-text {
    margin: 0;
    font-size: 0.85rem;
  }

  .fault-locations {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .fault-locations li {
    padding: 0.5rem;
    background: var(--bg-tertiary);
    border-radius: 4px;
    border-left: 3px solid #a855f7;
  }

  .location-badge {
    font-size: 0.65rem;
    font-weight: 600;
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    text-transform: uppercase;
  }

  .location-badge.general_prompt {
    background: #1e3a5f;
    color: #60a5fa;
  }

  .location-badge.node_prompt {
    background: #065f46;
    color: #34d399;
  }

  .location-badge.transition {
    background: #4c1d95;
    color: #a78bfa;
  }

  .location-badge.missing_transition {
    background: #78350f;
    color: #fbbf24;
  }

  .node-ref {
    font-size: 0.75rem;
    background: var(--bg-hover);
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
    margin-left: 0.25rem;
  }

  .relevant-text {
    font-size: 0.8rem;
    margin: 0.25rem 0;
    padding: 0.25rem 0.5rem;
    background: var(--bg-primary);
    border-radius: 3px;
    white-space: pre-wrap;
    color: var(--text-secondary);
  }

  .fault-explanation {
    font-size: 0.8rem;
    color: var(--text-secondary);
    display: block;
  }

  .transcript-evidence {
    margin: 0;
    padding: 0.5rem 0.75rem;
    border-left: 3px solid var(--border-color);
    font-size: 0.8rem;
    font-style: italic;
    color: var(--text-secondary);
    white-space: pre-wrap;
  }

  .fix-summary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 0.5rem;
  }

  .fix-summary p {
    margin: 0;
    font-size: 0.85rem;
    flex: 1;
  }

  .confidence-badge {
    font-size: 0.7rem;
    padding: 0.15rem 0.4rem;
    border-radius: 3px;
    background: #065f46;
    color: #34d399;
    font-weight: 600;
    white-space: nowrap;
  }

  .proposed-changes {
    list-style: none;
    padding: 0;
    margin: 0 0 0.75rem 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .proposed-changes li {
    padding: 0.5rem;
    background: var(--bg-tertiary);
    border-radius: 4px;
  }

  .change-diff {
    margin: 0.25rem 0;
    font-size: 0.8rem;
  }

  .change-diff del {
    display: block;
    background: rgba(248, 113, 113, 0.15);
    color: #f87171;
    text-decoration: line-through;
    padding: 0.25rem 0.5rem;
    border-radius: 3px 3px 0 0;
    white-space: pre-wrap;
  }

  .change-diff ins {
    display: block;
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    text-decoration: none;
    padding: 0.25rem 0.5rem;
    border-radius: 0 0 3px 3px;
    white-space: pre-wrap;
  }

  .proposed-text-edit {
    display: block;
    width: 100%;
    background: rgba(34, 197, 94, 0.1);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.3);
    border-radius: 0 0 3px 3px;
    padding: 0.25rem 0.5rem;
    font-family: monospace;
    font-size: 0.8rem;
    line-height: 1.4;
    resize: vertical;
    box-sizing: border-box;
  }

  .proposed-text-edit:focus {
    outline: none;
    border-color: #22c55e;
    background: rgba(34, 197, 94, 0.15);
  }

  .change-rationale {
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
  }

  .diagnosis-actions,
  .fix-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
  }

  .apply-btn,
  .save-btn {
    padding: 0.35rem 0.75rem !important;
    font-size: 0.8rem !important;
    background: var(--status-pass-bg) !important;
    color: var(--color-pass) !important;
    border: 1px solid rgba(63, 185, 80, 0.3) !important;
    cursor: pointer;
    font-weight: 600;
  }

  .apply-btn:hover:not(:disabled),
  .save-btn:hover:not(:disabled) {
    background: rgba(63, 185, 80, 0.25) !important;
  }

  .dismiss-btn {
    padding: 0.35rem 0.75rem !important;
    font-size: 0.8rem !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    color: var(--text-secondary) !important;
    cursor: pointer;
  }

  .dismiss-btn:hover {
    background: var(--bg-hover) !important;
  }

  .retry-btn {
    padding: 0.35rem 0.75rem !important;
    font-size: 0.8rem !important;
    background: #1e3a5f !important;
    border: 1px solid rgba(96, 165, 250, 0.3) !important;
    color: #60a5fa !important;
    cursor: pointer;
    font-weight: 600;
  }

  .retry-btn:hover:not(:disabled) {
    background: rgba(96, 165, 250, 0.2) !important;
  }

  .fix-result-panel {
    margin-top: 1rem;
    padding: 0.75rem;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
  }

  .score-comparison {
    width: 100%;
    font-size: 0.8rem;
    border-collapse: collapse;
    margin-bottom: 0.75rem;
  }

  .score-comparison th {
    text-align: left;
    padding: 0.35rem 0.5rem;
    border-bottom: 1px solid var(--border-color);
    color: var(--text-secondary);
    font-weight: 600;
    font-size: 0.75rem;
  }

  .score-comparison td {
    padding: 0.35rem 0.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .metric-cell {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .delta-positive {
    color: #34d399;
    font-weight: 600;
  }

  .delta-negative {
    color: #f87171;
    font-weight: 600;
  }

  .delta-neutral {
    color: var(--text-muted);
  }

  .fix-status {
    padding: 0.35rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    text-align: center;
  }

  .fix-status.pass {
    background: var(--status-pass-bg);
    color: var(--color-pass);
  }

  .fix-status.improved {
    background: #1e3a5f;
    color: #60a5fa;
  }

  .fix-status.no-improvement {
    background: var(--status-fail-bg);
    color: var(--color-fail);
  }
</style>
