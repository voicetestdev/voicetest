<script lang="ts">
  import { api } from "../lib/api";
  import {
    testCases,
    testCaseRecords,
    currentAgentId,
    currentAgent,
    agentGraph,
    isRunning,
    currentView,
    startRun,
  } from "../lib/stores";
  import type { TestCase, TestCaseRecord } from "../lib/types";

  let newTest = $state<Partial<TestCase>>({
    name: "",
    user_prompt: "",
    metrics: [],
    dynamic_variables: {},
    tool_mocks: [],
    type: "llm",
    llm_model: undefined,
    includes: [],
    excludes: [],
    patterns: [],
  });
  let metricInput = $state("");
  let includeInput = $state("");
  let excludeInput = $state("");
  let patternInput = $state("");
  let editingId = $state<string | null>(null);
  let jsonImport = $state("");
  let importError = $state("");
  let saving = $state(false);
  let showNewTestModal = $state(false);
  let showImportModal = $state(false);
  let showExportModal = $state(false);
  let selectedTestIds = $state<string[]>([]);
  let runError = $state("");
  let exportFormat = $state("retell");
  let exportSelection = $state<"all" | "selected">("all");
  let exporting = $state(false);
  let exportError = $state("");

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      if (showNewTestModal) {
        closeNewTestModal();
      } else if (showImportModal) {
        closeImportModal();
      } else if (showExportModal) {
        closeExportModal();
      }
    }
  }

  function parseRecord(record: TestCaseRecord): TestCase {
    return {
      name: record.name,
      user_prompt: record.user_prompt,
      metrics: record.metrics ? JSON.parse(record.metrics) : [],
      dynamic_variables: record.dynamic_variables
        ? JSON.parse(record.dynamic_variables)
        : {},
      tool_mocks: record.tool_mocks ? JSON.parse(record.tool_mocks) : [],
      type: record.type || "llm",
      llm_model: record.llm_model ?? undefined,
      includes: record.includes ? JSON.parse(record.includes) : [],
      excludes: record.excludes ? JSON.parse(record.excludes) : [],
      patterns: record.patterns ? JSON.parse(record.patterns) : [],
    };
  }

  async function refreshTests() {
    if (!$currentAgentId) return;
    const records = await api.listTestsForAgent($currentAgentId);
    testCaseRecords.set(records);
    testCases.set(records.map(parseRecord));
  }

  function addMetric() {
    if (metricInput.trim()) {
      newTest.metrics = [...(newTest.metrics || []), metricInput.trim()];
      metricInput = "";
    }
  }

  function removeMetric(index: number) {
    newTest.metrics = newTest.metrics?.filter((_, i) => i !== index) || [];
  }

  function addInclude() {
    if (includeInput.trim()) {
      newTest.includes = [...(newTest.includes || []), includeInput.trim()];
      includeInput = "";
    }
  }

  function removeInclude(index: number) {
    newTest.includes = newTest.includes?.filter((_, i) => i !== index) || [];
  }

  function addExclude() {
    if (excludeInput.trim()) {
      newTest.excludes = [...(newTest.excludes || []), excludeInput.trim()];
      excludeInput = "";
    }
  }

  function removeExclude(index: number) {
    newTest.excludes = newTest.excludes?.filter((_, i) => i !== index) || [];
  }

  function addPattern() {
    if (patternInput.trim()) {
      newTest.patterns = [...(newTest.patterns || []), patternInput.trim()];
      patternInput = "";
    }
  }

  function removePattern(index: number) {
    newTest.patterns = newTest.patterns?.filter((_, i) => i !== index) || [];
  }

  async function saveTest() {
    if (!newTest.name || !newTest.user_prompt || !$currentAgentId) return;

    saving = true;
    try {
      const testData = {
        name: newTest.name,
        user_prompt: newTest.user_prompt,
        metrics: newTest.metrics || [],
        dynamic_variables: newTest.dynamic_variables || {},
        tool_mocks: newTest.tool_mocks || [],
        type: newTest.type || "llm",
        llm_model: newTest.llm_model,
        includes: newTest.includes || [],
        excludes: newTest.excludes || [],
        patterns: newTest.patterns || [],
      };

      if (editingId) {
        await api.updateTestCase(editingId, testData);
      } else {
        await api.createTestCase($currentAgentId, testData);
      }

      await refreshTests();
      closeNewTestModal();
    } catch (e) {
      importError = e instanceof Error ? e.message : String(e);
    }
    saving = false;
  }

  function editTest(record: TestCaseRecord) {
    newTest = parseRecord(record);
    editingId = record.id;
    showNewTestModal = true;
  }

  async function deleteTest(id: string) {
    if (!confirm("Are you sure you want to delete this test?")) return;
    try {
      await api.deleteTestCase(id);
      await refreshTests();
      selectedTestIds = selectedTestIds.filter((x) => x !== id);
    } catch (e) {
      importError = e instanceof Error ? e.message : String(e);
    }
  }

  function resetForm() {
    newTest = {
      name: "",
      user_prompt: "",
      metrics: [],
      dynamic_variables: {},
      tool_mocks: [],
      type: "llm",
      llm_model: undefined,
      includes: [],
      excludes: [],
      patterns: [],
    };
    editingId = null;
    importError = "";
  }

  function openNewTestModal() {
    resetForm();
    showNewTestModal = true;
  }

  function closeNewTestModal() {
    showNewTestModal = false;
    resetForm();
  }

  function openImportModal() {
    jsonImport = "";
    importError = "";
    showImportModal = true;
  }

  function closeImportModal() {
    showImportModal = false;
    jsonImport = "";
    importError = "";
  }

  function normalizeTestType(type: string | undefined): string {
    if (type === "simulation") return "llm";
    if (type === "unit") return "rule";
    return type || "llm";
  }

  async function importFromJson() {
    if (!$currentAgentId) return;

    importError = "";
    saving = true;
    try {
      const parsed = JSON.parse(jsonImport);
      const tests = Array.isArray(parsed) ? parsed : [parsed];

      for (const test of tests) {
        await api.createTestCase($currentAgentId, {
          name: test.name,
          user_prompt: test.user_prompt,
          metrics: test.metrics || [],
          dynamic_variables: test.dynamic_variables || {},
          tool_mocks: test.tool_mocks || [],
          type: normalizeTestType(test.type),
          llm_model: test.llm_model,
          includes: test.includes || [],
          excludes: test.excludes || [],
          patterns: test.patterns || [],
        });
      }

      await refreshTests();
      closeImportModal();
    } catch (e) {
      importError = e instanceof Error ? e.message : String(e);
    }
    saving = false;
  }

  async function handleFileUpload(event: Event) {
    if (!$currentAgentId) return;

    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    importError = "";
    saving = true;

    try {
      const content = await file.text();
      const parsed = JSON.parse(content);
      const tests = Array.isArray(parsed) ? parsed : [parsed];

      for (const test of tests) {
        await api.createTestCase($currentAgentId, {
          name: test.name,
          user_prompt: test.user_prompt,
          metrics: test.metrics || [],
          dynamic_variables: test.dynamic_variables || {},
          tool_mocks: test.tool_mocks || [],
          type: normalizeTestType(test.type),
          llm_model: test.llm_model,
          includes: test.includes || [],
          excludes: test.excludes || [],
          patterns: test.patterns || [],
        });
      }

      await refreshTests();
      closeImportModal();
      input.value = "";
    } catch (e) {
      importError = e instanceof Error ? e.message : String(e);
    }
    saving = false;
  }

  function toggleTestSelection(id: string) {
    if (selectedTestIds.includes(id)) {
      selectedTestIds = selectedTestIds.filter((x) => x !== id);
    } else {
      selectedTestIds = [...selectedTestIds, id];
    }
  }

  function selectAllTests() {
    if (selectedTestIds.length === $testCaseRecords.length && $testCaseRecords.length > 0) {
      selectedTestIds = [];
    } else {
      selectedTestIds = $testCaseRecords.map((r) => r.id);
    }
  }

  function truncatePrompt(prompt: string, maxLength: number = 60): string {
    if (prompt.length <= maxLength) return prompt;
    return prompt.substring(0, maxLength) + "...";
  }

  async function runAllTests() {
    if (!$currentAgentId || $testCases.length === 0) return;

    runError = "";
    currentView.set("runs");

    try {
      await startRun($currentAgentId);
    } catch (e) {
      runError = e instanceof Error ? e.message : String(e);
    }
  }

  async function runSelectedTests() {
    if (!$currentAgentId || selectedTestIds.length === 0) return;

    currentView.set("runs");
    runError = "";

    try {
      await startRun($currentAgentId, selectedTestIds);
    } catch (e) {
      runError = e instanceof Error ? e.message : String(e);
    }
  }

  function openExportModal() {
    exportFormat = "retell";
    exportSelection = "all";
    exportError = "";
    showExportModal = true;
  }

  function closeExportModal() {
    showExportModal = false;
    exportError = "";
  }

  async function doExport() {
    if (!$currentAgentId) return;

    exporting = true;
    exportError = "";

    try {
      const testIds = exportSelection === "selected" ? selectedTestIds : undefined;
      const data = await api.exportTests($currentAgentId, exportFormat, testIds);

      const agentName = $currentAgent?.name || "tests";
      const safeName = agentName.replace(/[^a-zA-Z0-9_-]/g, "_");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${safeName}_tests_${exportFormat}.json`;
      a.click();
      URL.revokeObjectURL(url);

      closeExportModal();
    } catch (e) {
      exportError = e instanceof Error ? e.message : String(e);
    }

    exporting = false;
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="tests-view">
  <div class="header">
    <h2>Tests for {$currentAgent?.name}</h2>
    {#if $currentAgentId}
      <div class="header-actions">
        <button
          class="run-btn"
          onclick={runAllTests}
          disabled={$isRunning || !$agentGraph || $testCases.length === 0}
        >
          {$isRunning ? "Running..." : "Run All"}
        </button>
        <button
          class="run-btn secondary"
          onclick={runSelectedTests}
          disabled={$isRunning || !$agentGraph || selectedTestIds.length === 0}
        >
          Run Selected ({selectedTestIds.length})
        </button>
        <button class="secondary" onclick={openNewTestModal}>+ New Test</button>
        <button class="secondary" onclick={openImportModal}>Import</button>
        <button
          class="secondary"
          onclick={openExportModal}
          disabled={$testCaseRecords.length === 0}
        >Export</button>
      </div>
    {/if}
  </div>

  {#if !$currentAgentId}
    <p class="placeholder">No agent selected.</p>
  {:else}
    <div class="layout">
      <section class="test-list-section">
        {#if $testCaseRecords.length === 0}
          <p class="empty">No test cases yet. Click "New Test" or "Import" to add tests.</p>
        {:else}
          <table class="test-table">
            <thead>
              <tr>
                <th class="col-select">
                  <input
                    type="checkbox"
                    checked={selectedTestIds.length === $testCaseRecords.length && $testCaseRecords.length > 0}
                    onchange={selectAllTests}
                  />
                </th>
                <th class="col-name">Name</th>
                <th class="col-type">Type</th>
                <th class="col-prompt">Prompt</th>
                <th class="col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {#each $testCaseRecords as record}
                <tr class:selected={selectedTestIds.includes(record.id)}>
                  <td class="col-select">
                    <input
                      type="checkbox"
                      checked={selectedTestIds.includes(record.id)}
                      onchange={() => toggleTestSelection(record.id)}
                    />
                  </td>
                  <td class="col-name">{record.name}</td>
                  <td class="col-type">
                    <span class="tag {record.type}">{record.type}</span>
                  </td>
                  <td class="col-prompt">
                    <span class="prompt-preview">{truncatePrompt(record.user_prompt)}</span>
                  </td>
                  <td class="col-actions">
                    <button class="small" onclick={() => editTest(record)}>Edit</button>
                    <button class="small danger" onclick={() => deleteTest(record.id)}>Delete</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}

        {#if runError}
          <p class="error-message">{runError}</p>
        {/if}
      </section>
    </div>
  {/if}
</div>

{#if showNewTestModal}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_interactive_supports_focus a11y_click_events_have_key_events -->
  <div class="modal-backdrop" role="dialog" aria-modal="true" onclick={closeNewTestModal}>
    <!-- svelte-ignore a11y_no_static_element_interactions a11y_click_events_have_key_events -->
    <div class="modal" role="document" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h3>{editingId ? "Edit Test" : "New Test"}</h3>
        <button class="close-btn" onclick={closeNewTestModal}>x</button>
      </div>
      <div class="modal-body">
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
          <label for="test-type">Type</label>
          <select id="test-type" bind:value={newTest.type}>
            <option value="llm">LLM (semantic evaluation)</option>
            <option value="rule">Rule (pattern matching)</option>
          </select>
        </div>

        <div class="form-group">
          <label for="test-llm-model">LLM Model (optional)</label>
          <input
            id="test-llm-model"
            type="text"
            bind:value={newTest.llm_model}
            placeholder="e.g., groq/llama-3.1-8b-instant (leave empty for default)"
          />
          <span class="field-hint">Override the agent model for this specific test</span>
        </div>

        {#if newTest.type === "llm" || newTest.type === "simulation"}
          <div class="form-group">
            <label for="metric-input">Metrics</label>
            <div class="input-row">
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
              <ul class="tag-list">
                {#each newTest.metrics as metric, i}
                  <li>
                    <span>{metric}</span>
                    <button class="small danger" onclick={() => removeMetric(i)}>x</button>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        {:else}
          <div class="form-group">
            <label for="include-input">Must Include</label>
            <div class="input-row">
              <input
                id="include-input"
                type="text"
                bind:value={includeInput}
                placeholder="Substring that must be present..."
                onkeydown={(e) => e.key === "Enter" && addInclude()}
              />
              <button type="button" onclick={addInclude}>Add</button>
            </div>
            {#if newTest.includes && newTest.includes.length > 0}
              <ul class="tag-list includes">
                {#each newTest.includes as item, i}
                  <li>
                    <span>{item}</span>
                    <button class="small danger" onclick={() => removeInclude(i)}>x</button>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <div class="form-group">
            <label for="exclude-input">Must Exclude</label>
            <div class="input-row">
              <input
                id="exclude-input"
                type="text"
                bind:value={excludeInput}
                placeholder="Substring that must NOT be present..."
                onkeydown={(e) => e.key === "Enter" && addExclude()}
              />
              <button type="button" onclick={addExclude}>Add</button>
            </div>
            {#if newTest.excludes && newTest.excludes.length > 0}
              <ul class="tag-list excludes">
                {#each newTest.excludes as item, i}
                  <li>
                    <span>{item}</span>
                    <button class="small danger" onclick={() => removeExclude(i)}>x</button>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <div class="form-group">
            <label for="pattern-input">Regex Patterns</label>
            <div class="input-row">
              <input
                id="pattern-input"
                type="text"
                bind:value={patternInput}
                placeholder="Regex pattern to match..."
                onkeydown={(e) => e.key === "Enter" && addPattern()}
              />
              <button type="button" onclick={addPattern}>Add</button>
            </div>
            {#if newTest.patterns && newTest.patterns.length > 0}
              <ul class="tag-list patterns">
                {#each newTest.patterns as item, i}
                  <li>
                    <code>{item}</code>
                    <button class="small danger" onclick={() => removePattern(i)}>x</button>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        {/if}

        {#if importError}
          <p class="error-message">{importError}</p>
        {/if}
      </div>
      <div class="modal-footer">
        <button class="secondary" onclick={closeNewTestModal}>Cancel</button>
        <button
          onclick={saveTest}
          disabled={!newTest.name || !newTest.user_prompt || saving}
        >
          {saving ? "Saving..." : editingId ? "Update Test" : "Create Test"}
        </button>
      </div>
    </div>
  </div>
{/if}

{#if showImportModal}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_interactive_supports_focus a11y_click_events_have_key_events -->
  <div class="modal-backdrop" role="dialog" aria-modal="true" onclick={closeImportModal}>
    <!-- svelte-ignore a11y_no_static_element_interactions a11y_click_events_have_key_events -->
    <div class="modal" role="document" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h3>Import Tests</h3>
        <button class="close-btn" onclick={closeImportModal}>x</button>
      </div>
      <div class="modal-body">
        <div class="file-upload">
          <label for="file-input" class="file-label">
            Choose File
            <input
              id="file-input"
              type="file"
              accept=".json,application/json"
              onchange={handleFileUpload}
            />
          </label>
          <span class="file-hint">or paste JSON below</span>
        </div>
        <textarea
          bind:value={jsonImport}
          placeholder="Paste test case JSON (single or array)..."
          rows={10}
        ></textarea>
        {#if importError}
          <p class="error-message">{importError}</p>
        {/if}
      </div>
      <div class="modal-footer">
        <button class="secondary" onclick={closeImportModal}>Cancel</button>
        <button onclick={importFromJson} disabled={!jsonImport || saving}>
          {saving ? "Importing..." : "Import"}
        </button>
      </div>
    </div>
  </div>
{/if}

{#if showExportModal}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_interactive_supports_focus a11y_click_events_have_key_events -->
  <div class="modal-backdrop" role="dialog" aria-modal="true" onclick={closeExportModal}>
    <!-- svelte-ignore a11y_no_static_element_interactions a11y_click_events_have_key_events -->
    <div class="modal" role="document" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h3>Export Tests</h3>
        <button class="close-btn" onclick={closeExportModal}>x</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="export-format">Format</label>
          <select id="export-format" bind:value={exportFormat}>
            <option value="retell">Retell</option>
          </select>
        </div>

        <div class="form-group">
          <label for="export-selection">Tests</label>
          <select id="export-selection" bind:value={exportSelection}>
            <option value="all">All tests ({$testCaseRecords.length})</option>
            <option value="selected" disabled={selectedTestIds.length === 0}>
              Selected tests ({selectedTestIds.length})
            </option>
          </select>
        </div>

        {#if exportError}
          <p class="error-message">{exportError}</p>
        {/if}
      </div>
      <div class="modal-footer">
        <button class="secondary" onclick={closeExportModal}>Cancel</button>
        <button onclick={doExport} disabled={exporting}>
          {exporting ? "Exporting..." : "Export"}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .tests-view {
    max-width: 1400px;
    overflow-y: auto;
    flex: 1;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }

  h2 {
    margin: 0;
  }

  h3 {
    margin: 0;
    font-size: 1rem;
    color: var(--text-secondary);
  }

  .header-actions {
    display: flex;
    gap: 0.5rem;
  }

  .run-btn {
    min-width: 100px;
    background: var(--accent);
    color: #ffffff;
    border-color: var(--accent);
  }

  .run-btn:hover:not(:disabled) {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
  }

  .run-btn.secondary {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    border-color: var(--border-color);
  }

  .run-btn.secondary:hover:not(:disabled) {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .placeholder {
    color: var(--text-secondary);
    font-style: italic;
  }

  .layout {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .test-list-section {
    background: var(--bg-secondary);
    padding: var(--space-4);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
  }

  .test-table {
    width: 100%;
    border-collapse: collapse;
  }

  .test-table th,
  .test-table td {
    padding: var(--space-2) var(--space-3);
    text-align: left;
    border-bottom: 1px solid var(--border-color);
  }

  .test-table th {
    color: var(--text-secondary);
    font-weight: 500;
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .test-table tbody tr {
    transition: background 80ms ease-out;
  }

  .test-table tbody tr:hover {
    background: var(--bg-hover);
  }

  .test-table tbody tr.selected {
    background: var(--bg-tertiary);
  }

  .col-select {
    width: 40px;
  }

  .col-name {
    width: 25%;
    font-weight: 500;
  }

  .col-type {
    width: 80px;
  }

  .col-prompt {
    width: auto;
  }

  .col-actions {
    width: 140px;
    text-align: right;
  }

  .prompt-preview {
    color: var(--text-secondary);
    font-size: 0.85rem;
  }

  .tag {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 9999px;
    font-size: var(--text-xs);
    font-weight: 500;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
  }

  .tag.llm {
    background: rgba(136, 87, 229, 0.15);
    color: #a78bfa;
    border-color: rgba(136, 87, 229, 0.3);
  }

  .tag.rule {
    background: rgba(63, 185, 80, 0.15);
    color: var(--color-pass);
    border-color: rgba(63, 185, 80, 0.3);
  }

  .small {
    padding: 0.2rem 0.4rem;
    font-size: var(--text-xs);
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

  .danger {
    background: transparent;
    color: var(--danger-text);
    border: 1px solid var(--border-color);
  }

  .danger:hover {
    background: var(--danger-bg-hover);
    border-color: var(--danger-border);
  }

  .empty {
    color: var(--text-muted);
    font-style: italic;
    padding: 2rem;
    text-align: center;
  }

  .error-message {
    color: #f87171;
    margin: 0.5rem 0 0 0;
    font-size: 0.85rem;
  }

  /* Modal styles */
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    width: 90%;
    max-width: 600px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-4);
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-tertiary);
  }

  .modal-header h3 {
    color: var(--text-primary);
    font-size: var(--text-sm);
  }

  .close-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 1.25rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
  }

  .close-btn:hover {
    color: var(--text-primary);
    background: transparent;
  }

  .modal-body {
    padding: var(--space-4);
    overflow-y: auto;
    flex: 1;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    padding: var(--space-4);
    border-top: 1px solid var(--border-color);
    background: var(--bg-tertiary);
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-group label {
    display: block;
    margin-bottom: 0.25rem;
    color: var(--text-secondary);
    font-size: 0.85rem;
  }

  .form-group input,
  .form-group textarea,
  .form-group select {
    width: 100%;
  }

  .form-group select {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 0.5rem;
    border-radius: 4px;
  }

  .field-hint {
    display: block;
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.25rem;
  }

  .input-row {
    display: flex;
    gap: 0.5rem;
  }

  .input-row input {
    flex: 1;
  }

  .tag-list {
    list-style: none;
    padding: 0;
    margin: 0.5rem 0 0 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .tag-list li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--bg-primary);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.85rem;
  }

  .tag-list.includes li {
    border-left: 3px solid #4ade80;
  }

  .tag-list.excludes li {
    border-left: 3px solid #f87171;
  }

  .tag-list.patterns li {
    border-left: 3px solid #60a5fa;
  }

  .tag-list code {
    font-family: monospace;
    font-size: 0.8rem;
  }

  .file-upload {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.75rem;
  }

  .file-label {
    display: inline-block;
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
  }

  .file-label:hover {
    background: #2563eb;
  }

  .file-label input {
    display: none;
  }

  .file-hint {
    color: var(--text-muted);
    font-size: 0.85rem;
  }

  @media (max-width: 768px) {
    .test-list-section {
      max-width: 100%;
    }
  }
</style>
