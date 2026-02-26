<script lang="ts">
  import { api } from "../lib/api";
  import {
    agentGraph,
  } from "../lib/stores";
  import type { DryAnalysis } from "../lib/types";

  interface Props {
    agentId: string;
    snippets: Record<string, string>;
    onerror?: (msg: string) => void;
  }

  let { agentId, snippets = $bindable({}), onerror }: Props = $props();

  let addingSnippet = $state(false);
  let newSnippetName = $state("");
  let newSnippetText = $state("");
  let savingSnippet = $state(false);
  let editingSnippetName = $state<string | null>(null);
  let editedSnippetText = $state("");
  let dryAnalysis = $state<DryAnalysis | null>(null);
  let analyzingDry = $state(false);
  let applyingSnippets = $state(false);

  $effect(() => {
    if (agentId) {
      api.getSnippets(agentId).then((data) => {
        snippets = data.snippets;
      }).catch(() => {
        snippets = {};
      });
      dryAnalysis = null;
    } else {
      snippets = {};
      dryAnalysis = null;
    }
  });

  function reportError(msg: string) {
    onerror?.(msg);
  }

  async function addSnippet() {
    if (!agentId || !newSnippetName.trim() || !newSnippetText.trim()) return;
    savingSnippet = true;
    try {
      const result = await api.updateSnippet(agentId, newSnippetName.trim(), newSnippetText.trim());
      snippets = result.snippets;
      newSnippetName = "";
      newSnippetText = "";
      addingSnippet = false;
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    savingSnippet = false;
  }

  async function saveEditedSnippet() {
    if (!agentId || !editingSnippetName) return;
    savingSnippet = true;
    try {
      const result = await api.updateSnippet(agentId, editingSnippetName, editedSnippetText);
      snippets = result.snippets;
      editingSnippetName = null;
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    savingSnippet = false;
  }

  async function removeSnippet(name: string) {
    if (!agentId) return;
    try {
      const result = await api.deleteSnippet(agentId, name);
      snippets = result.snippets;
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
  }

  async function runDryAnalysis() {
    if (!agentId) return;
    analyzingDry = true;
    dryAnalysis = null;
    try {
      dryAnalysis = await api.analyzeDry(agentId);
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    analyzingDry = false;
  }

  async function applySingleSnippet(name: string, text: string) {
    if (!agentId) return;
    applyingSnippets = true;
    try {
      const result = await api.applySnippets(agentId, [{ name, text }]);
      agentGraph.set(result);
      snippets = result.snippets ?? {};
      dryAnalysis = null;
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    applyingSnippets = false;
  }

  async function applyAllExactSnippets() {
    if (!agentId || !dryAnalysis) return;
    applyingSnippets = true;
    try {
      const items = dryAnalysis.exact.map((m, i) => ({
        name: `snippet_${i + 1}`,
        text: m.text,
      }));
      const result = await api.applySnippets(agentId, items);
      agentGraph.set(result);
      snippets = result.snippets ?? {};
      dryAnalysis = null;
    } catch (e) {
      reportError(e instanceof Error ? e.message : String(e));
    }
    applyingSnippets = false;
  }
</script>

<section class="snippets-section">
  <div class="snippets-header">
    <h3>Snippets</h3>
    <div class="snippets-actions">
      <button class="btn-sm" onclick={() => { addingSnippet = !addingSnippet; }} title="Add a snippet">+ Add</button>
      <button class="btn-sm" onclick={runDryAnalysis} disabled={analyzingDry} title="Analyze prompts for repeated text">
        {analyzingDry ? "Analyzing..." : "Analyze DRY"}
      </button>
    </div>
  </div>

  {#if Object.keys(snippets).length > 0}
    <div class="snippet-list">
      {#each Object.entries(snippets) as [name, text]}
        <div class="snippet-item">
          <div class="snippet-name-row">
            <code class="snippet-ref">{"{%"}{name}{"%}"}</code>
            <div class="snippet-btns">
              <button class="btn-xs" onclick={() => { editingSnippetName = name; editedSnippetText = text; }}>Edit</button>
              <button class="btn-xs danger-text" onclick={() => removeSnippet(name)}>Delete</button>
            </div>
          </div>
          {#if editingSnippetName === name}
            <textarea
              class="snippet-textarea"
              bind:value={editedSnippetText}
              disabled={savingSnippet}
              rows="3"
            ></textarea>
            <div class="snippet-edit-actions">
              <button class="btn-xs" onclick={() => { editingSnippetName = null; }}>Cancel</button>
              <button class="btn-xs btn-primary" onclick={saveEditedSnippet} disabled={savingSnippet}>Save</button>
            </div>
          {:else}
            <pre class="snippet-preview">{text}</pre>
          {/if}
        </div>
      {/each}
    </div>
  {:else if !addingSnippet}
    <p class="snippet-empty">No snippets defined. Use "Analyze DRY" to find repeated text or add snippets manually.</p>
  {/if}

  {#if addingSnippet}
    <div class="snippet-add-form">
      <input type="text" placeholder="Snippet name" class="snippet-name-input" bind:value={newSnippetName} />
      <textarea
        class="snippet-textarea"
        placeholder="Snippet text..."
        bind:value={newSnippetText}
        rows="3"
      ></textarea>
      <div class="snippet-edit-actions">
        <button class="btn-xs" onclick={() => { addingSnippet = false; newSnippetName = ""; newSnippetText = ""; }}>Cancel</button>
        <button class="btn-xs btn-primary" onclick={addSnippet} disabled={savingSnippet || !newSnippetName.trim() || !newSnippetText.trim()}>
          {savingSnippet ? "Saving..." : "Add Snippet"}
        </button>
      </div>
    </div>
  {/if}

  {#if dryAnalysis}
    <div class="dry-results">
      <div class="dry-header">
        <h4>DRY Analysis Results</h4>
        {#if dryAnalysis.exact.length > 0}
          <button class="btn-sm" onclick={applyAllExactSnippets} disabled={applyingSnippets}>
            {applyingSnippets ? "Applying..." : `Apply All (${dryAnalysis.exact.length})`}
          </button>
        {/if}
      </div>

      {#if dryAnalysis.exact.length === 0 && dryAnalysis.fuzzy.length === 0}
        <p class="dry-empty">No repeated text found. Prompts are already DRY.</p>
      {/if}

      {#if dryAnalysis.exact.length > 0}
        <div class="dry-section">
          <h5>Exact Matches</h5>
          {#each dryAnalysis.exact as match, i}
            <div class="dry-match">
              <pre class="dry-text">{match.text}</pre>
              <div class="dry-meta">
                <span class="dry-locations">Found in: {match.locations.join(", ")}</span>
                <button
                  class="btn-xs"
                  onclick={() => applySingleSnippet(`snippet_${i + 1}`, match.text)}
                  disabled={applyingSnippets}
                >Apply</button>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      {#if dryAnalysis.fuzzy.length > 0}
        <div class="dry-section">
          <h5>Similar Text ({dryAnalysis.fuzzy.length})</h5>
          {#each dryAnalysis.fuzzy as match}
            <div class="dry-match">
              <div class="dry-similarity">{Math.round(match.similarity * 100)}% similar</div>
              {#each match.texts as text, ti}
                <pre class="dry-text">{match.locations[ti]}: {text}</pre>
              {/each}
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</section>
