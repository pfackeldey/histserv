import { describe, it, expect, vi, beforeEach } from 'vitest'
import { get } from 'svelte/store'

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
Object.defineProperty(globalThis, 'location', {
  value: { protocol: 'http:', host: 'localhost' },
  writable: true,
})

// Import after mocking
const { histKey, histogramData, subscribeHist, unsubscribeHist } =
  await import('../lib/stores/histogramData')

function sentMessages(): { type: string; payload: Record<string, unknown> }[] {
  return MockWS.instance.sent.map((raw) => JSON.parse(raw))
}

function receive(payload: Record<string, unknown>) {
  MockWS.instance.onmessage?.({
    data: JSON.stringify({ type: 'hist_data', ts: 1000, payload }),
  })
}

describe('histKey', () => {
  it('is independent of selection key order', () => {
    expect(histKey('h', { a: 1, b: 'x' })).toBe(histKey('h', { b: 'x', a: 1 }))
  })

  it('distinguishes different selections of the same histogram', () => {
    expect(histKey('h', { cat: 'a' })).not.toBe(histKey('h', { cat: 'b' }))
  })
})

describe('histogramData store', () => {
  beforeEach(() => {
    MockWS.instance?.onopen?.()
    MockWS.instance.sent = []
    histogramData.set(new Map())
  })

  it('keeps different selections of the same histogram separately', () => {
    receive({ hist_id: 'h', selection: { cat: 'a' }, values: [1], version: 1 })
    receive({ hist_id: 'h', selection: { cat: 'b' }, values: [2], version: 1 })

    const data = get(histogramData)
    expect(data.get(histKey('h', { cat: 'a' }))?.values).toEqual([1])
    expect(data.get(histKey('h', { cat: 'b' }))?.values).toEqual([2])
  })

  it('subscribeHist sends the token only when set', () => {
    subscribeHist('h', { cat: 'a' }, 'secret')
    subscribeHist('h', { cat: 'b' })

    const [withToken, withoutToken] = sentMessages()
    expect(withToken.payload.token).toBe('secret')
    expect('token' in withoutToken.payload).toBe(false)

    unsubscribeHist('h', { cat: 'a' })
    unsubscribeHist('h', { cat: 'b' })
  })

  it('unsubscribeHist drops only the matching selection', () => {
    receive({ hist_id: 'h', selection: { cat: 'a' }, values: [1], version: 1 })
    receive({ hist_id: 'h', selection: { cat: 'b' }, values: [2], version: 1 })

    unsubscribeHist('h', { cat: 'a' })

    const data = get(histogramData)
    expect(data.has(histKey('h', { cat: 'a' }))).toBe(false)
    expect(data.get(histKey('h', { cat: 'b' }))?.values).toEqual([2])
  })

  it('re-subscribes active histogram subscriptions on reconnect', () => {
    vi.useFakeTimers()
    try {
      subscribeHist('h', { cat: 'a' }, 'secret', 2.0)
      const initial = MockWS.instance

      // Drop the connection; the store reconnects after a delay.
      initial.onclose?.()
      vi.advanceTimersByTime(5000)
      expect(MockWS.instance).not.toBe(initial) // a new socket was opened
      MockWS.instance.onopen?.()

      // The new connection carries the subscription again.
      const resent = sentMessages().filter((m) => m.type === 'subscribe_hist')
      expect(resent).toHaveLength(1)
      expect(resent.at(-1)?.payload).toMatchObject({
        hist_id: 'h',
        selection: { cat: 'a' },
        token: 'secret',
        rate_limit_hz: 2.0,
      })

      unsubscribeHist('h', { cat: 'a' })
    } finally {
      vi.useRealTimers()
    }
  })
})
