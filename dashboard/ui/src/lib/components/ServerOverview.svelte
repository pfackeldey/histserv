<script lang="ts">
  import { stats } from '../stores/stats'

  function formatBytes(n: number): string {
    if (n < 1024) return `${n} B`
    if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
    if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
    return `${(n / 1024 ** 3).toFixed(2)} GB`
  }

  function totalRpcCalls(counts: Record<string, number>): number {
    return Object.values(counts).reduce((a, b) => a + b, 0)
  }

  function rpcBreakdown(counts: Record<string, number>): string {
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}: ${v}`)
      .join(', ')
  }

  function formatUptime(s: number): string {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = Math.floor(s % 60)
    return h > 0 ? `${h}h ${m}m ${sec}s` : m > 0 ? `${m}m ${sec}s` : `${sec}s`
  }
</script>

<section class="overview">
  <h2>Server Overview</h2>
  {#if $stats}
    <div class="cards">
      <div class="card">
        <span class="label">Version</span>
        <span class="value">{$stats.version}</span>
      </div>
      <div class="card">
        <span class="label">Uptime</span>
        <span class="value">{formatUptime($stats.uptime_seconds)}</span>
      </div>
      <div class="card">
        <span class="label">Histograms</span>
        <span class="value">{$stats.histogram_count}</span>
      </div>
      <div class="card">
        <span class="label">Memory</span>
        <span class="value">{formatBytes($stats.histogram_bytes)}</span>
      </div>
      <div class="card">
        <span class="label">Active RPCs</span>
        <span class="value">{$stats.active_rpcs}</span>
      </div>
      <div class="card" title={rpcBreakdown($stats.rpc_calls_total)}>
        <span class="label">Total RPC Calls</span>
        <span class="value">{totalRpcCalls($stats.rpc_calls_total)}</span>
      </div>
    </div>
  {:else}
    <p class="waiting">Waiting for server data…</p>
  {/if}
</section>

<style>
  .overview {
    padding: 1rem;
  }
  h2 {
    margin: 0 0 0.75rem;
    font-size: 1rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-muted, #888);
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.75rem;
  }
  .card {
    background: var(--color-card, #1e1e2e);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-muted, #888);
  }
  .value {
    font-size: 1.25rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .waiting {
    color: var(--color-muted, #888);
    font-style: italic;
  }
</style>
