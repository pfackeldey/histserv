<script lang="ts">
  import { createEventDispatcher } from 'svelte'
  import type { HistMetaPayload } from '../types/protocol'

  const dispatch = createEventDispatcher<{
    view: {
      hist_id: string
      token: string | null
      selection: Record<string, string | number>
      meta: HistMetaPayload
    }
  }>()

  let histId = ''
  let token = ''
  let loading = false
  let error: string | null = null
  let meta: HistMetaPayload | null = null

  // Per-chunk-axis selection values chosen by user
  let chunkSelections: Record<string, string | number> = {}

  async function lookup() {
    const id = histId.trim()
    if (!id) return
    loading = true
    error = null
    meta = null
    chunkSelections = {}
    try {
      const params = new URLSearchParams()
      if (token.trim()) params.set('token', token.trim())
      const resp = await fetch(`/api/histograms/${encodeURIComponent(id)}/metadata?${params}`)
      if (resp.status === 404) {
        error = 'Histogram not found. Check the ID and token.'
        return
      }
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({ error: resp.statusText }))) as {
          error?: string
        }
        error = body.error ?? `Server error (${resp.status})`
        return
      }
      meta = (await resp.json()) as HistMetaPayload
      // Pre-select the first category for each chunk axis
      for (const ax of meta.chunk_axes) {
        chunkSelections[ax.name] = ax.categories[0]
      }
    } catch {
      error = 'Network error. Is the server running?'
    } finally {
      loading = false
    }
  }

  function addView() {
    if (!meta) return
    dispatch('view', {
      hist_id: meta.hist_id,
      token: token.trim() || null,
      selection: { ...chunkSelections },
      meta,
    })
  }

  function denseAxisDesc(m: HistMetaPayload): string {
    return m.dense_metadata.axes
      .map((ax) => {
        const name = ax.metadata?.name ?? ''
        if (ax.type === 'regular') return `${name}[${ax.bins}]`
        if (ax.type === 'variable') return `${name}[${ax.edges.length - 1}]`
        if (ax.type === 'category_str' || ax.type === 'category_int')
          return `${name}[${ax.categories.length}]`
        return name
      })
      .join(' × ')
  }
</script>

<section class="lookup">
  <h2>Inspect Histogram</h2>
  <p class="hint">
    Get your histogram ID from Python:
    <code>remote_hist.get_connection_info()</code>
  </p>

  <form class="form" on:submit|preventDefault={lookup}>
    <div class="row">
      <label class="field field--grow">
        <span>Histogram ID</span>
        <input
          bind:value={histId}
          placeholder="e.g. 20a3c7cce3104cdc9e7a2eb1fee0d196"
          autocomplete="off"
          spellcheck="false"
          class="mono"
        />
      </label>
      <label class="field">
        <span>Token <span class="optional">(optional)</span></span>
        <input bind:value={token} type="password" placeholder="—" autocomplete="off" />
      </label>
      <button type="submit" class="btn" disabled={loading || !histId.trim()}>
        {loading ? 'Looking up…' : 'Look up'}
      </button>
    </div>
  </form>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if meta}
    <div class="meta-panel">
      <div class="meta-row">
        <span class="meta-key">Axes</span>
        <span class="meta-val mono">{denseAxisDesc(meta)}</span>
      </div>
      <div class="meta-row">
        <span class="meta-key">Storage</span>
        <span class="meta-val mono">{meta.dense_metadata.storage.type}</span>
      </div>
      {#if meta.dense_metadata.metadata.name}
        <div class="meta-row">
          <span class="meta-key">Name</span>
          <span class="meta-val">{meta.dense_metadata.metadata.name}</span>
        </div>
      {/if}

      {#if meta.chunk_axes.length > 0}
        <div class="slice-section">
          <span class="slice-label">Select slice:</span>
          {#each meta.chunk_axes as ax (ax.name)}
            <label class="slice-field">
              <span class="slice-axis-name">{ax.label || ax.name}</span>
              <select bind:value={chunkSelections[ax.name]}>
                {#each ax.categories as cat (cat)}
                  <option value={cat}>{cat}</option>
                {/each}
              </select>
            </label>
          {/each}
        </div>
      {/if}

      <button class="btn btn--primary" on:click={addView}>
        View {meta.chunk_axes.length > 0 ? 'Slice' : 'Histogram'}
      </button>
    </div>
  {/if}
</section>

<style>
  .lookup {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--color-border, #333);
  }
  h2 {
    margin: 0 0 0.25rem;
    font-size: 0.875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-muted, #888);
  }
  .hint {
    margin: 0 0 0.75rem;
    font-size: 0.78rem;
    color: var(--color-muted, #888);
  }
  .hint code {
    background: rgba(255, 255, 255, 0.07);
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 0.76rem;
    font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  }
  .form {
    margin-bottom: 0.5rem;
  }
  .row {
    display: flex;
    gap: 0.5rem;
    align-items: flex-end;
    flex-wrap: wrap;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--color-muted, #888);
  }
  .field--grow {
    flex: 1 1 240px;
  }
  .field input,
  .slice-field select {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--color-border, #333);
    border-radius: 4px;
    color: var(--color-fg, #e0e0f0);
    padding: 0.35rem 0.6rem;
    font-size: 0.8rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .field input:focus,
  .slice-field select:focus {
    border-color: rgba(96, 170, 255, 0.5);
  }
  .mono {
    font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  }
  .optional {
    font-weight: 400;
    font-style: italic;
    opacity: 0.6;
  }
  .btn {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid var(--color-border, #333);
    border-radius: 4px;
    color: var(--color-fg, #e0e0f0);
    cursor: pointer;
    font-size: 0.8rem;
    padding: 0.38rem 0.85rem;
    white-space: nowrap;
    transition:
      background 0.15s,
      border-color 0.15s;
    align-self: flex-end;
  }
  .btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.13);
    border-color: rgba(96, 170, 255, 0.4);
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .btn--primary {
    background: rgba(96, 170, 255, 0.15);
    border-color: rgba(96, 170, 255, 0.4);
    color: #60aaff;
    font-weight: 600;
    margin-top: 0.75rem;
  }
  .btn--primary:hover {
    background: rgba(96, 170, 255, 0.25);
  }
  .error {
    color: #df6f6f;
    font-size: 0.8rem;
    margin: 0.25rem 0 0;
    background: rgba(223, 111, 111, 0.08);
    border: 1px solid rgba(223, 111, 111, 0.25);
    border-radius: 4px;
    padding: 0.4rem 0.7rem;
  }
  .meta-panel {
    margin-top: 0.75rem;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--color-border, #333);
    border-radius: 6px;
    padding: 0.75rem;
  }
  .meta-row {
    display: flex;
    gap: 0.75rem;
    align-items: baseline;
    font-size: 0.8rem;
    margin-bottom: 0.3rem;
  }
  .meta-key {
    color: var(--color-muted, #888);
    min-width: 5rem;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .meta-val {
    color: var(--color-fg, #e0e0f0);
  }
  .slice-section {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-top: 0.5rem;
  }
  .slice-label {
    color: var(--color-muted, #888);
    font-size: 0.75rem;
  }
  .slice-field {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.78rem;
    color: var(--color-muted, #888);
  }
  .slice-axis-name {
    font-family: 'JetBrains Mono', 'Fira Mono', monospace;
    font-size: 0.75rem;
  }
</style>
