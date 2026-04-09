<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from 'svelte'
  import { histogramData, subscribeHist, unsubscribeHist } from '../stores/histogramData'
  import { renderHistogram } from '../d3-histogram'
  import type { HistMetaPayload } from '../types/protocol'

  export let hist_id: string
  export let selection: Record<string, string | number>
  export let meta: HistMetaPayload

  const dispatch = createEventDispatcher<{ close: void }>()

  let container: SVGSVGElement
  let lastVersion: number | null = null

  onMount(() => {
    subscribeHist(hist_id, selection)
  })

  onDestroy(() => {
    unsubscribeHist(hist_id, selection)
  })

  $: data = $histogramData.get(hist_id) ?? null

  // Re-render only when version changes (new data arrived)
  $: if (container && data && data.version !== lastVersion) {
    lastVersion = data.version
    renderHistogram(container, data, meta)
  }

  function histName(): string {
    return meta.dense_metadata.metadata.name || hist_id.slice(0, 12)
  }

  function histLabel(): string {
    return meta.dense_metadata.metadata.label ?? ''
  }

  function dimDesc(m: HistMetaPayload): string {
    const axes = m.dense_metadata.axes
    const names = axes.map((a) => a.metadata?.name ?? '').filter(Boolean)
    return `${axes.length}D${names.length ? ' · ' + names.join(' × ') : ''}`
  }

  function selectionTags(sel: Record<string, string | number>): string[] {
    return Object.entries(sel).map(([k, v]) => `${k}=${v}`)
  }
</script>

<div class="hist-view">
  <div class="header">
    <div class="header-left">
      <span class="name">{histName()}</span>
      {#if histLabel()}
        <span class="label">{histLabel()}</span>
      {/if}
      {#each selectionTags(selection) as tag (tag)}
        <span class="tag">{tag}</span>
      {/each}
    </div>
    <div class="header-right">
      <span class="dim">{dimDesc(meta)}</span>
      <button class="close-btn" on:click={() => dispatch('close')} title="Remove this view"
        >×</button
      >
    </div>
  </div>

  {#if data}
    <svg bind:this={container} class="chart"></svg>
  {:else}
    <div class="loading">Loading {hist_id.slice(0, 12)}…</div>
  {/if}
</div>

<style>
  .hist-view {
    background: var(--color-card, #1e1e2e);
    border-radius: 8px;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .header-left {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    flex-wrap: wrap;
    min-width: 0;
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }
  .name {
    font-weight: 700;
    font-size: 1rem;
  }
  .label {
    color: var(--color-muted, #888);
    font-size: 0.85rem;
  }
  .tag {
    font-family: 'JetBrains Mono', 'Fira Mono', monospace;
    font-size: 0.7rem;
    background: rgba(96, 170, 255, 0.12);
    border: 1px solid rgba(96, 170, 255, 0.25);
    border-radius: 3px;
    padding: 1px 5px;
    color: #60aaff;
  }
  .dim {
    font-size: 0.75rem;
    font-family: monospace;
    color: var(--color-muted, #888);
  }
  .close-btn {
    background: none;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    color: var(--color-muted, #888);
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: 1px 6px;
    transition:
      color 0.15s,
      border-color 0.15s;
  }
  .close-btn:hover {
    color: var(--color-fg, #e0e0f0);
    border-color: rgba(255, 255, 255, 0.3);
  }
  .chart {
    width: 100%;
    height: 300px;
    display: block;
  }
  .loading {
    color: var(--color-muted, #888);
    font-style: italic;
    padding: 2rem;
    text-align: center;
  }
</style>
