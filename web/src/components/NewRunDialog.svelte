<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { RunResult, TestCaseRecord } from '../lib/types';
	import { api } from '../lib/api';

	interface Props {
		agentId: string;
		open: boolean;
		onclose: () => void;
		onsubmit: (testIds: string[]) => Promise<RunResult | void>;
		extras?: Snippet;
	}

	let { agentId, open, onclose, onsubmit, extras }: Props = $props();

	let tests = $state<TestCaseRecord[]>([]);
	let selectedTestIds = $state<string[]>([]);
	let loadingTests = $state(false);
	let submitting = $state(false);
	let submitError = $state<string | null>(null);
	let submitResult = $state<RunResult | null>(null);

	$effect(() => {
		if (open && agentId) {
			loadTests(agentId);
		}
		if (!open) {
			reset();
		}
	});

	async function loadTests(id: string) {
		loadingTests = true;
		submitError = null;
		submitResult = null;
		selectedTestIds = [];
		try {
			tests = await api.listTestsForAgent(id);
		} catch {
			tests = [];
		} finally {
			loadingTests = false;
		}
	}

	function reset() {
		submitError = null;
		submitResult = null;
		selectedTestIds = [];
	}

	function toggleTest(testId: string) {
		if (selectedTestIds.includes(testId)) {
			selectedTestIds = selectedTestIds.filter((id) => id !== testId);
		} else {
			selectedTestIds = [...selectedTestIds, testId];
		}
	}

	function selectAll() {
		selectedTestIds = tests.map((t) => t.id);
	}

	function clearSelection() {
		selectedTestIds = [];
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (selectedTestIds.length === 0) return;
		submitting = true;
		submitError = null;
		try {
			const result = await onsubmit(selectedTestIds);
			if (result) {
				submitResult = result;
			} else {
				onclose();
			}
		} catch (err) {
			submitError = err instanceof Error ? err.message : 'Failed to start run';
		} finally {
			submitting = false;
		}
	}

	function handleBackdropClick() {
		onclose();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) {
			onclose();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div class="modal-backdrop" onclick={handleBackdropClick}>
		<div class="modal" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
			<div class="modal-header">
				<h3>Start New Run</h3>
				<button class="close-btn" onclick={onclose}>&times;</button>
			</div>

			{#if submitResult}
				<div class="modal-body">
					<div class="success-message">
						<div class="success-icon">&#10003;</div>
						<h3>Run Queued</h3>
						{#if submitResult.message}
							<p>{submitResult.message}</p>
						{/if}
						<p class="run-id">Run ID: <code>{submitResult.run_id}</code></p>
						{#if submitResult.details}
							<p class="run-details">
								{#each Object.entries(submitResult.details) as [key, value]}
									{key}: {value}
									{' '}
								{/each}
							</p>
						{/if}
						<button class="btn btn-primary" onclick={onclose}>Close</button>
					</div>
				</div>
			{:else}
				<form class="modal-body" onsubmit={handleSubmit}>
					{#if submitError}
						<div class="error-message">{submitError}</div>
					{/if}

					{#if extras}
						{@render extras()}
					{/if}

					<div class="form-group">
						<label>
							Tests to Run
							{#if tests.length > 0}
								<span class="test-count">({selectedTestIds.length} of {tests.length} selected)</span>
							{/if}
						</label>

						{#if loadingTests}
							<div class="loading">Loading tests...</div>
						{:else if tests.length === 0}
							<div class="no-tests">No tests found for this agent. Create tests first.</div>
						{:else}
							<div class="test-actions">
								<button type="button" class="btn btn-sm" onclick={selectAll}>Select All</button>
								<button type="button" class="btn btn-sm" onclick={clearSelection}>Clear</button>
							</div>
							<div class="test-list">
								{#each tests as test}
									<label class="test-item" class:selected={selectedTestIds.includes(test.id)}>
										<input
											type="checkbox"
											checked={selectedTestIds.includes(test.id)}
											onchange={() => toggleTest(test.id)}
										/>
										<span class="test-name">{test.name}</span>
									</label>
								{/each}
							</div>
						{/if}
					</div>

					<div class="modal-footer">
						<button type="button" class="btn" onclick={onclose}>Cancel</button>
						<button
							type="submit"
							class="btn btn-primary"
							disabled={selectedTestIds.length === 0 || submitting}
						>
							{#if submitting}
								Running...
							{:else}
								Start Run ({selectedTestIds.length} tests)
							{/if}
						</button>
					</div>
				</form>
			{/if}
		</div>
	</div>
{/if}

<style>
	.modal {
		width: 90%;
		max-width: 500px;
		max-height: 80vh;
	}

	.form-group {
		margin-bottom: 1.25rem;
	}

	.form-group label {
		display: block;
		margin-bottom: 0.5rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.btn {
		padding: 0.5rem 1rem;
		border-radius: 6px;
		font-size: 0.875rem;
		cursor: pointer;
		border: 1px solid var(--border-color);
		background: var(--bg-secondary);
		color: var(--text-primary);
		transition: all 0.2s;
	}

	.btn:hover:not(:disabled) {
		background: var(--bg-tertiary);
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--accent, #3b82f6);
		border-color: var(--accent, #3b82f6);
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		opacity: 0.9;
	}

	.btn-sm {
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
	}

	.test-count {
		font-weight: normal;
		color: var(--text-secondary);
		font-size: 0.875rem;
	}

	.test-actions {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.test-list {
		max-height: 250px;
		overflow-y: auto;
		border: 1px solid var(--border-color);
		border-radius: 6px;
	}

	.test-item {
		position: relative;
		display: block;
		min-height: 2.5rem;
		padding: 0.5rem 0.75rem 0.5rem 2.5rem;
		cursor: pointer;
		border-bottom: 1px solid var(--border-color);
		transition: background 0.2s;
	}

	.test-item:last-child {
		border-bottom: none;
	}

	.test-item:hover {
		background: rgba(255, 255, 255, 0.03);
	}

	.test-item.selected {
		background: rgba(59, 130, 246, 0.1);
	}

	.test-item input[type='checkbox'] {
		position: absolute;
		left: 0.75rem;
		top: 50%;
		transform: translateY(-50%);
		width: 18px;
		height: 18px;
		margin: 0;
	}

	.test-name {
		display: block;
		font-weight: 500;
		line-height: 1.4;
		overflow-wrap: anywhere;
	}

	.loading,
	.no-tests {
		padding: 1rem;
		text-align: center;
		color: var(--text-secondary);
		background: var(--bg);
		border: 1px solid var(--border-color);
		border-radius: 6px;
	}

	.error-message {
		padding: 0.75rem;
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.3);
		border-radius: 6px;
		color: var(--error, #ef4444);
		margin-bottom: 1rem;
	}

	.success-message {
		text-align: center;
		padding: 1rem;
	}

	.success-icon {
		width: 48px;
		height: 48px;
		background: rgba(34, 197, 94, 0.2);
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.5rem;
		color: #22c55e;
		margin: 0 auto 1rem;
	}

	.success-message h3 {
		margin: 0 0 0.5rem;
	}

	.success-message p {
		color: var(--text-secondary);
		margin: 0 0 0.5rem;
	}

	.run-id {
		margin-bottom: 0.5rem;
	}

	.run-id code {
		background: var(--bg);
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		font-size: 0.75rem;
	}

	.run-details {
		margin-bottom: 1.5rem;
	}
</style>
