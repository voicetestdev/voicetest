<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import { testCases } from "../lib/stores";
  import type { TestCase } from "../lib/types";

  interface Props {
    agentId: string;
    mode: "chat" | "call";
    onclose: () => void;
    onlaunch: (variables: Record<string, unknown>) => void;
  }

  let { agentId, mode, onclose, onlaunch }: Props = $props();

  let variableNames = $state<string[]>([]);
  let variableValues = $state<Record<string, string>>({});
  let loading = $state(true);
  let error = $state<string | null>(null);
  let cases = $derived($testCases);

  onMount(async () => {
    try {
      const result = await api.getAgentVariables(agentId);
      variableNames = result.variables;

      if (variableNames.length === 0) {
        onlaunch({});
        return;
      }

      const initial: Record<string, string> = {};
      for (const name of variableNames) {
        initial[name] = "";
      }
      variableValues = initial;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });

  function handleTestCaseSelect(e: Event) {
    const select = e.target as HTMLSelectElement;
    const testId = select.value;
    if (!testId) return;

    const testCase = cases.find((tc: TestCase) => tc.name === testId);
    if (!testCase?.dynamic_variables) return;

    const updated = { ...variableValues };
    for (const name of variableNames) {
      const val = testCase.dynamic_variables[name];
      if (val !== undefined) {
        updated[name] = String(val);
      }
    }
    variableValues = updated;
  }

  function handleLaunch() {
    const vars: Record<string, unknown> = {};
    for (const name of variableNames) {
      const val = variableValues[name];
      if (val) {
        vars[name] = val;
      }
    }
    onlaunch(vars);
  }

  function handleBackdropClick() {
    onclose();
  }

  function handleModalClick(e: MouseEvent) {
    e.stopPropagation();
  }
</script>

{#if loading}
  <!-- loading, nothing to show -->
{:else if error}
  <div class="modal-backdrop" role="dialog" aria-modal="true" onclick={handleBackdropClick}>
    <div class="modal" role="document" onclick={handleModalClick}>
      <div class="modal-header">
        <h3>Error</h3>
        <button class="close-btn" onclick={onclose}>x</button>
      </div>
      <div class="modal-body">
        <p class="error-text">{error}</p>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick={onclose}>Close</button>
      </div>
    </div>
  </div>
{:else}
  <div class="modal-backdrop" role="dialog" aria-modal="true" onclick={handleBackdropClick}>
    <div class="modal" role="document" onclick={handleModalClick}>
      <div class="modal-header">
        <h3>{mode === "chat" ? "Chat" : "Call"} Variables</h3>
        <button class="close-btn" onclick={onclose}>x</button>
      </div>
      <div class="modal-body">
        {#if cases.length > 0}
          <div class="form-group">
            <label for="test-case-select">Pre-fill from test case</label>
            <select id="test-case-select" class="form-select" onchange={handleTestCaseSelect}>
              <option value="">Select a test case...</option>
              {#each cases as tc}
                <option value={tc.name}>{tc.name}</option>
              {/each}
            </select>
          </div>
        {/if}

        <div class="variables-list">
          {#each variableNames as name}
            <div class="form-group">
              <label for="var-{name}">{name}</label>
              <input
                id="var-{name}"
                type="text"
                class="form-input"
                bind:value={variableValues[name]}
                placeholder="Enter value for {name}"
              />
            </div>
          {/each}
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick={onclose}>Cancel</button>
        <button class="btn-primary" onclick={handleLaunch}>Launch</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal {
    width: 90%;
    max-width: 480px;
  }

  .form-group {
    margin-bottom: var(--space-3);
  }

  .form-group label {
    display: block;
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: var(--space-1);
  }

  .form-select,
  .form-input {
    width: 100%;
    padding: 0.4rem 0.6rem;
    font-size: 0.85rem;
    background: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    outline: none;
    box-sizing: border-box;
  }

  .form-select:focus,
  .form-input:focus {
    border-color: var(--accent);
  }

  .variables-list {
    margin-top: var(--space-2);
  }

  .error-text {
    color: var(--danger-text);
    font-size: 0.85rem;
  }
</style>
