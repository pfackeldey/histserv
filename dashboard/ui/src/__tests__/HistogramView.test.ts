import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/svelte'
import { histogramData } from '../lib/stores/histogramData'
import { histogramMeta } from '../lib/stores/histogramMeta'
import type { HistDataPayload, HistMetaPayload } from '../lib/types/protocol'

// Mock the websocket store so subscribeHist/unsubscribeHist are no-ops in tests
vi.mock('../lib/stores/websocket', () => ({
  wsStatus: { subscribe: vi.fn(() => () => {}) },
  send: vi.fn(),
  onMessage: vi.fn(() => () => {}),
}))

// Import component after mocking
const { default: HistogramView } = await import('../lib/components/HistogramView.svelte')

const mockData: HistDataPayload = {
  hist_id: 'test123',
  selection: {},
  // 4 bins + underflow + overflow = 6 values (flow bins will be trimmed by renderer)
  values: [0, 1, 2, 3, 4, 0],
  version: 1712500000000,
}

const mockMeta: HistMetaPayload = {
  hist_id: 'test123',
  dense_metadata: {
    uhi_schema: 1,
    axes: [
      {
        type: 'regular',
        lower: 0,
        upper: 4,
        bins: 4,
        underflow: true,
        overflow: true,
        circular: false,
        metadata: { name: 'x', label: 'x-axis' },
      },
    ],
    storage: { type: 'double' },
    metadata: { name: 'my_hist', label: 'My Histogram' },
  },
  chunk_axes: [],
}

describe('HistogramView', () => {
  beforeEach(() => {
    histogramData.set(new Map())
    histogramMeta.set(new Map())
  })

  it('shows loading state when no data', () => {
    histogramMeta.set(new Map([['test123', mockMeta]]))
    const { getByText } = render(HistogramView, {
      props: { hist_id: 'test123', selection: {}, meta: mockMeta },
    })
    expect(getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders histogram name when data available', () => {
    histogramData.set(new Map([['test123', mockData]]))
    histogramMeta.set(new Map([['test123', mockMeta]]))
    const { getByText } = render(HistogramView, {
      props: { hist_id: 'test123', selection: {}, meta: mockMeta },
    })
    expect(getByText('my_hist')).toBeInTheDocument()
  })

  it('renders histogram label', () => {
    histogramData.set(new Map([['test123', mockData]]))
    histogramMeta.set(new Map([['test123', mockMeta]]))
    const { getByText } = render(HistogramView, {
      props: { hist_id: 'test123', selection: {}, meta: mockMeta },
    })
    expect(getByText('My Histogram')).toBeInTheDocument()
  })

  it('renders dimension description', () => {
    histogramData.set(new Map([['test123', mockData]]))
    histogramMeta.set(new Map([['test123', mockMeta]]))
    const { getByText } = render(HistogramView, {
      props: { hist_id: 'test123', selection: {}, meta: mockMeta },
    })
    // Should show "1D · x"
    expect(getByText(/1D/)).toBeInTheDocument()
  })

  it('renders svg chart element when data available', () => {
    histogramData.set(new Map([['test123', mockData]]))
    histogramMeta.set(new Map([['test123', mockMeta]]))
    const { container } = render(HistogramView, {
      props: { hist_id: 'test123', selection: {}, meta: mockMeta },
    })
    expect(container.querySelector('svg')).toBeTruthy()
  })
})
