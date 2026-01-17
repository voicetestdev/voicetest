<script lang="ts">
  import { testCases, selectedTestId } from "../lib/stores";
  import type { TestCase } from "../lib/types";

  let newTest = $state<Partial<TestCase>>({
    name: "",
    user_prompt: "",
    metrics: [],
    dynamic_variables: {},
    tool_mocks: [],
    type: "simulation",
  });
  let metricInput = $state("");
  let editing = $state<string | null>(null);
  let jsonImport = $state("");
  let importError = $state("");

  function addMetric() {
    if (metricInput.trim()) {
      newTest.metrics = [...(newTest.metrics || []), metricInput.trim()];
      metricInput = "";
    }
  }

  function removeMetric(index: number) {
    newTest.metrics = newTest.metrics?.filter((_, i) => i !== index) || [];
  }

  function saveTest() {
    if (!newTest.name || !newTest.user_prompt) return;

    const test: TestCase = {
      name: newTest.name,
      user_prompt: newTest.user_prompt,
      metrics: newTest.metrics || [],
      dynamic_variables: newTest.dynamic_variables || {},
      tool_mocks: newTest.tool_mocks || [],
      type: newTest.type || "simulation",
      llm_model: newTest.llm_model || undefined,
    };

    if (editing) {
      testCases.update((cases) =>
        cases.map((c) => (c.name === editing ? test : c))
      );
      editing = null;
    } else {
      testCases.update((cases) => [...cases, test]);
    }

    resetForm();
  }

  function editTest(test: TestCase) {
    newTest = { ...test };
    editing = test.name;
  }

  function deleteTest(name: string) {
    testCases.update((cases) => cases.filter((c) => c.name !== name));
    if (editing === name) {
      resetForm();
    }
  }

  function resetForm() {
    newTest = {
      name: "",
      user_prompt: "",
      metrics: [],
      dynamic_variables: {},
      tool_mocks: [],
      type: "simulation",
    };
    editing = null;
  }

  function importFromJson() {
    importError = "";
    try {
      const parsed = JSON.parse(jsonImport);
      const tests = Array.isArray(parsed) ? parsed : [parsed];
      testCases.update((cases) => [...cases, ...tests]);
      jsonImport = "";
    } catch (e) {
      importError = e instanceof Error ? e.message : String(e);
    }
  }

  function selectTest(name: string) {
    selectedTestId.set(name);
  }
</script>

<div class="tests-view">
  <h2>Test Cases</h2>

  <div class="layout">
    <section class="test-list">
      <h3>Tests ({$testCases.length})</h3>
      {#if $testCases.length === 0}
        <p class="empty">No test cases loaded</p>
      {:else}
        <ul>
          {#each $testCases as test}
            <li class:selected={$selectedTestId === test.name}>
              <button
                type="button"
                class="test-select-btn"
                onclick={() => selectTest(test.name)}
              >
                <div class="test-header">
                  <span class="test-name">{test.name}</span>
                  <span class="test-type tag">{test.type}</span>
                </div>
              </button>
              <div class="test-actions">
                <button class="small" onclick={() => editTest(test)}>
                  Edit
                </button>
                <button
                  class="small danger"
                  onclick={() => deleteTest(test.name)}
                >
                  Delete
                </button>
              </div>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section class="test-editor">
      <h3>{editing ? "Edit Test" : "New Test"}</h3>

      <div class="form-group">
        <label for="test-name">Name</label>
        <input
          id="test-name"
          type="text"
          bind:value={newTest.name}
          placeholder="Test name"
        />
      </div>

      <div class="form-group">
        <label for="test-prompt">User Prompt</label>
        <textarea
          id="test-prompt"
          bind:value={newTest.user_prompt}
          placeholder="The initial prompt to start the conversation..."
          rows={4}
        ></textarea>
      </div>

      <div class="form-group">
        <label for="metric-input">Metrics</label>
        <div class="metric-input">
          <input
            id="metric-input"
            type="text"
            bind:value={metricInput}
            placeholder="Add evaluation criteria..."
            onkeydown={(e) => e.key === "Enter" && addMetric()}
          />
          <button type="button" onclick={addMetric}>Add</button>
        </div>
        {#if newTest.metrics && newTest.metrics.length > 0}
          <ul class="metrics-list">
            {#each newTest.metrics as metric, i}
              <li>
                <span>{metric}</span>
                <button class="small danger" onclick={() => removeMetric(i)}>
                  x
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <div class="form-group">
        <label for="test-type">Type</label>
        <select id="test-type" bind:value={newTest.type}>
          <option value="simulation">Simulation</option>
          <option value="unit">Unit</option>
        </select>
      </div>

      <div class="button-row">
        <button onclick={saveTest} disabled={!newTest.name || !newTest.user_prompt}>
          {editing ? "Update Test" : "Add Test"}
        </button>
        {#if editing}
          <button class="secondary" onclick={resetForm}>Cancel</button>
        {/if}
      </div>
    </section>

    <section class="import-section">
      <h3>Import from JSON</h3>
      <textarea
        bind:value={jsonImport}
        placeholder="Paste test case JSON (single or array)..."
        rows={6}
      ></textarea>
      <button onclick={importFromJson} disabled={!jsonImport}>
        Import
      </button>
      {#if importError}
        <p class="error-message">{importError}</p>
      {/if}
    </section>
  </div>
</div>

<style>
  .tests-view {
    max-width: 1200px;
  }

  h2 {
    margin-top: 0;
  }

  h3 {
    margin-top: 0;
    font-size: 1rem;
    color: #9ca3af;
  }

  .layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto;
    gap: 1.5rem;
  }

  .test-list {
    grid-row: span 2;
  }

  .test-list ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .test-list li {
    background: #16213e;
    border-radius: 4px;
    border: 1px solid transparent;
  }

  .test-list li:hover {
    border-color: #374151;
  }

  .test-list li.selected {
    border-color: #3b82f6;
  }

  .test-select-btn {
    width: 100%;
    background: transparent;
    border: none;
    padding: 0.75rem;
    padding-bottom: 0;
    cursor: pointer;
    text-align: left;
    color: inherit;
  }

  .test-select-btn:hover {
    background: transparent;
  }

  .test-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .test-actions {
    display: flex;
    gap: 0.5rem;
    padding: 0 0.75rem 0.75rem 0.75rem;
  }

  .test-name {
    font-weight: 500;
  }

  .tag {
    background: #374151;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
  }

  .small {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }

  .danger {
    background: #dc2626;
  }

  .danger:hover {
    background: #b91c1c;
  }

  .empty {
    color: #6b7280;
    font-style: italic;
  }

  .test-editor,
  .import-section {
    background: #16213e;
    padding: 1rem;
    border-radius: 8px;
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

  .form-group input,
  .form-group textarea,
  .form-group select {
    width: 100%;
  }

  .form-group select {
    background: #1a1a2e;
    border: 1px solid #374151;
    color: #e8e8e8;
    padding: 0.5rem;
    border-radius: 4px;
  }

  .metric-input {
    display: flex;
    gap: 0.5rem;
  }

  .metric-input input {
    flex: 1;
  }

  .metrics-list {
    list-style: none;
    padding: 0;
    margin: 0.5rem 0 0 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .metrics-list li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #1a1a2e;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.85rem;
  }

  .button-row {
    display: flex;
    gap: 0.5rem;
  }

  .secondary {
    background: #374151;
  }

  .secondary:hover {
    background: #4b5563;
  }

  .error-message {
    color: #f87171;
    margin: 0.5rem 0 0 0;
    font-size: 0.85rem;
  }
</style>
