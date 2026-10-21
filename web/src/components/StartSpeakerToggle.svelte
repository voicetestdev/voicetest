<script lang="ts">
  import { START_SPEAKER_LABELS } from "../lib/types";
  import type { StartSpeaker } from "../lib/types";

  interface Props {
    value: StartSpeaker;
    onselect: (speaker: StartSpeaker) => void;
    disabled?: boolean;
    label?: string;
  }

  let { value, onselect, disabled = false, label = "Speaks first" }: Props = $props();

  const options = Object.keys(START_SPEAKER_LABELS) as StartSpeaker[];
</script>

<div class="segmented" role="group" aria-label={label}>
  {#each options as speaker}
    <button
      type="button"
      class:active={speaker === value}
      aria-pressed={speaker === value}
      {disabled}
      onclick={() => onselect(speaker)}
    >
      {START_SPEAKER_LABELS[speaker]}
    </button>
  {/each}
</div>

<style>
  .segmented {
    display: inline-flex;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    overflow: hidden;
  }

  button {
    background: var(--bg-secondary);
    color: var(--text-secondary);
    border: none;
    border-radius: 0;
    padding: 0.1rem 0.6rem;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  button + button {
    border-left: 1px solid var(--border-color);
  }

  button:hover:not(:disabled):not(.active) {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  button.active {
    background: var(--accent);
    color: #fff;
  }

  button:disabled {
    cursor: default;
    opacity: 0.6;
  }
</style>
