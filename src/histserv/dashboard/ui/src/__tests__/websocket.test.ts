import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock WebSocket before importing stores
class MockWS {
  static OPEN = 1
  readyState = MockWS.OPEN
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  constructor(public url: string) {
    MockWS.instance = this
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.onclose?.()
  }

  static instance: MockWS
}

vi.stubGlobal('WebSocket', MockWS)
// location is available in jsdom but we need to make sure host is set
Object.defineProperty(globalThis, 'location', {
  value: { protocol: 'http:', host: 'localhost' },
  writable: true,
})

// Import after mocking
const { onMessage, send } = await import('../lib/stores/websocket')

describe('WebSocket store', () => {
  beforeEach(() => {
    // Simulate open
    MockWS.instance?.onopen?.()
  })

  it('send() serializes message as JSON', () => {
    send({ type: 'get_hist', payload: { hist_id: 'abc123', selection: {} } })
    const last = MockWS.instance.sent.at(-1)!
    expect(JSON.parse(last)).toMatchObject({
      type: 'get_hist',
      payload: { hist_id: 'abc123', selection: {} },
    })
  })

  it('onMessage routes by type', () => {
    const handler = vi.fn()
    const unsub = onMessage('stats', handler)

    MockWS.instance.onmessage?.({
      data: JSON.stringify({
        type: 'stats',
        ts: 1000,
        payload: { histogram_count: 5, uptime_seconds: 10 },
      }),
    })

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].payload.histogram_count).toBe(5)
    unsub()
  })

  it('onMessage routes hist_meta by type', () => {
    const handler = vi.fn()
    const unsub = onMessage('hist_meta', handler)

    MockWS.instance.onmessage?.({
      data: JSON.stringify({
        type: 'hist_meta',
        ts: 1000,
        payload: {
          hist_id: 'test123',
          dense_metadata: { uhi_schema: 1, axes: [], storage: { type: 'double' }, metadata: {} },
          chunk_axes: [],
        },
      }),
    })

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].payload.hist_id).toBe('test123')
    unsub()
  })

  it('unsubscribe removes handler', () => {
    const handler = vi.fn()
    const unsub = onMessage('stats', handler)
    unsub()

    MockWS.instance.onmessage?.({
      data: JSON.stringify({ type: 'stats', ts: 1000, payload: { histogram_count: 3 } }),
    })

    expect(handler).not.toHaveBeenCalled()
  })

  it('onMessage does not call handlers for different types', () => {
    const statsHandler = vi.fn()
    const unsub = onMessage('stats', statsHandler)

    MockWS.instance.onmessage?.({
      data: JSON.stringify({ type: 'hist_data', ts: 1000, payload: { hist_id: 'x' } }),
    })

    expect(statsHandler).not.toHaveBeenCalled()
    unsub()
  })

  it('ignores malformed JSON without throwing', () => {
    expect(() => {
      MockWS.instance.onmessage?.({ data: 'not json' })
    }).not.toThrow()
  })
})
