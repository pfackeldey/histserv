import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/svelte'
import { stats } from '../lib/stores/stats'
import ServerOverview from '../lib/components/ServerOverview.svelte'
import type { StatsPayload } from '../lib/types/protocol'

const mockStats: StatsPayload = {
  histogram_count: 7,
  histogram_bytes: 1536,
  active_rpcs: 2,
  version: '1.2.3',
  uptime_seconds: 3725,
  cpu_user: 0.5,
  cpu_system: 0.1,
  rpc_calls_total: { Init: 2, Fill: 35, Snapshot: 5 },
  observed_at: Date.now() / 1000,
}

describe('ServerOverview', () => {
  it('shows waiting message when no stats', () => {
    stats.set(null)
    const { getByText } = render(ServerOverview)
    expect(getByText(/waiting/i)).toBeInTheDocument()
  })

  it('renders histogram count', () => {
    stats.set(mockStats)
    const { getByText } = render(ServerOverview)
    expect(getByText('7')).toBeInTheDocument()
  })

  it('renders version', () => {
    stats.set(mockStats)
    const { getByText } = render(ServerOverview)
    expect(getByText('1.2.3')).toBeInTheDocument()
  })

  it('formats memory in KB', () => {
    stats.set(mockStats)
    const { getByText } = render(ServerOverview)
    // 1536 bytes → 1.5 KB
    expect(getByText('1.5 KB')).toBeInTheDocument()
  })

  it('formats uptime with hours', () => {
    stats.set(mockStats) // 3725s = 1h 2m 5s
    const { getByText } = render(ServerOverview)
    expect(getByText('1h 2m 5s')).toBeInTheDocument()
  })

  it('sums rpc_calls_total across all methods', () => {
    stats.set(mockStats) // Init: 2 + Fill: 35 + Snapshot: 5 = 42
    const { getByText } = render(ServerOverview)
    expect(getByText('42')).toBeInTheDocument()
  })
})
