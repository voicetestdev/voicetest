<script lang="ts">
  import {
    runHistory,
    loadRun,
    currentRunId,
  } from "../lib/stores";
  import type { RunRecord } from "../lib/types";
  import ListPanel from "./ListPanel.svelte";

  function formatTimestamp(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return "now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);

    const isToday = date.toDateString() === now.toDateString();
    if (isToday) return `${diffHours}h ago`;

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = date.toDateString() === yesterday.toDateString();
    if (isYesterday) return "yesterday";

    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const sameYear = date.getFullYear() === now.getFullYear();
    if (sameYear) {
      return `${months[date.getMonth()]} ${date.getDate()}`;
    }
    return `${months[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
  }

  function formatDuration(run: RunRecord): string {
    if (!run.completed_at) return "";
    const start = new Date(run.started_at).getTime();
    const end = new Date(run.completed_at).getTime();
    const seconds = Math.floor((end - start) / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  }

  function getRunStatus(run: RunRecord): "pass" | "fail" | "running" | "empty" {
    const s = run.summary;
    if (!s || s.total === 0) return "empty";
    if (s.running > 0) return "running";
    if (s.failed > 0 || s.errors > 0) return "fail";
    return "pass";
  }

  function getSummaryText(run: RunRecord): string {
    const s = run.summary;
    if (!s || s.total === 0) return "No results";
    if (s.running > 0) {
      const done = s.passed + s.failed + s.errors;
      return `Running (${done}/${s.total} complete)`;
    }
    const parts: string[] = [];
    parts.push(`${s.passed} passed`);
    if (s.failed > 0) parts.push(`${s.failed} failed`);
    if (s.errors > 0) parts.push(`${s.errors} errors`);
    return parts.join(", ");
  }

  const MAX_FAILED_NAMES = 3;

  function getFailedNamesText(run: RunRecord): string | null {
    const names = run.summary?.failed_names ?? [];
    if (names.length === 0) return null;
    const shown = names.slice(0, MAX_FAILED_NAMES).join(", ");
    const remaining = names.length - MAX_FAILED_NAMES;
    return remaining > 0 ? `${shown} + ${remaining} more` : shown;
  }

  async function selectRun(runId: string) {
    await loadRun(runId);
  }
</script>

<div class="runs-list">
  {#if $runHistory.length === 0}
    <div class="empty-state">
      <p>No runs yet</p>
      <p class="hint">Run tests from the Tests tab to see results here.</p>
    </div>
  {:else}
    <ListPanel>
      <ul>
        {#each $runHistory as run}
          {@const status = getRunStatus(run)}
          {@const failedText = getFailedNamesText(run)}
          {@const duration = formatDuration(run)}
          <li>
            <button
              class="{status}"
              class:selected={$currentRunId === run.id}
              onclick={() => selectRun(run.id)}
            >
              <div class="run-card-left">
                <span class="status-icon {status}">
                  {#if status === "pass"}
                    <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                      <path fill-rule="evenodd" d="M8 16A8 8 0 108 0a8 8 0 000 16zm3.78-9.72a.75.75 0 00-1.06-1.06L6.75 9.19 5.28 7.72a.75.75 0 00-1.06 1.06l2 2a.75.75 0 001.06 0l4.5-4.5z"/>
                    </svg>
                  {:else if status === "fail"}
                    <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                      <path fill-rule="evenodd" d="M8 16A8 8 0 108 0a8 8 0 000 16zM5.28 4.22a.75.75 0 00-1.06 1.06L6.94 8 4.22 10.72a.75.75 0 101.06 1.06L8 9.06l2.72 2.72a.75.75 0 101.06-1.06L9.06 8l2.72-2.72a.75.75 0 00-1.06-1.06L8 6.94 5.28 4.22z"/>
                    </svg>
                  {:else if status === "running"}
                    <span class="mini-spinner"></span>
                  {:else}
                    <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/>
                    </svg>
                  {/if}
                </span>
              </div>
              <div class="run-card-body">
                <span class="summary-text">{getSummaryText(run)}</span>
                {#if run.summary && run.summary.total > 0}
                  <div class="run-card-detail">
                    <div class="progress-bar">
                      {#if run.summary.passed > 0}
                        <div class="progress-segment pass" style="width: {(run.summary.passed / run.summary.total) * 100}%"></div>
                      {/if}
                      {#if run.summary.failed > 0}
                        <div class="progress-segment fail" style="width: {(run.summary.failed / run.summary.total) * 100}%"></div>
                      {/if}
                      {#if run.summary.errors > 0}
                        <div class="progress-segment error" style="width: {(run.summary.errors / run.summary.total) * 100}%"></div>
                      {/if}
                      {#if run.summary.running > 0}
                        <div class="progress-segment running" style="width: {(run.summary.running / run.summary.total) * 100}%"></div>
                      {/if}
                    </div>
                    {#if failedText}
                      <span class="failed-names">{failedText}</span>
                    {/if}
                  </div>
                {/if}
              </div>
              <div class="run-card-right">
                <span class="run-time">{formatTimestamp(run.started_at)}</span>
                {#if duration}
                  <span class="run-duration">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" class="clock-icon">
                      <path fill-rule="evenodd" d="M8 0a8 8 0 110 16A8 8 0 018 0zm.5 4.75a.75.75 0 00-1.5 0v3.5c0 .199.079.39.22.53l2 2a.75.75 0 101.06-1.06L8.5 7.94V4.75z"/>
                    </svg>
                    {duration}
                  </span>
                {/if}
              </div>
            </button>
          </li>
        {/each}
      </ul>
    </ListPanel>
  {/if}
</div>

<style>
  .runs-list {
    height: 100%;
    overflow-y: auto;
    padding: var(--space-4);
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 200px;
    color: var(--text-secondary);
    font-size: var(--text-sm);
  }

  .empty-state .hint {
    color: var(--text-tertiary);
    margin-top: var(--space-2);
  }

  .run-card-left {
    flex-shrink: 0;
    padding-top: 2px;
  }

  .status-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
  }

  .status-icon.pass {
    color: var(--status-pass, #3fb950);
  }

  .status-icon.fail {
    color: var(--status-fail, #f85149);
  }

  .status-icon.running {
    color: var(--accent-blue, #60a5fa);
  }

  .status-icon.empty {
    color: var(--text-tertiary);
  }

  .mini-spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--border-color);
    border-top-color: currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .run-card-body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .summary-text {
    font-weight: 500;
    line-height: 1.4;
  }

  .run-card-detail {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .progress-bar {
    display: flex;
    height: 6px;
    width: 120px;
    flex-shrink: 0;
    border-radius: 3px;
    overflow: hidden;
    background: var(--bg-primary, #0d1117);
  }

  .progress-segment.pass {
    background: var(--status-pass, #3fb950);
  }

  .progress-segment.fail {
    background: var(--status-fail, #f85149);
  }

  .progress-segment.error {
    background: var(--status-error, #d29922);
  }

  .progress-segment.running {
    background: var(--accent-blue, #60a5fa);
  }

  .failed-names {
    color: var(--text-tertiary);
    font-size: var(--text-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .run-card-right {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    padding-top: 1px;
  }

  .run-time {
    color: var(--text-tertiary);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .run-duration {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--text-tertiary);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .clock-icon {
    opacity: 0.6;
  }
</style>
