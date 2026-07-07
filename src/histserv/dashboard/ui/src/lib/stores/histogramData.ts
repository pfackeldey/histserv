import { writable } from 'svelte/store'
import type { HistDataPayload } from '../types/protocol'
import { onMessage, onOpen, send } from './websocket'
import { histogramMeta } from './histogramMeta'

export type Selection = Record<string, string | number>

// Canonical key for one histogram slice. Selections are serialized as sorted
// [axis, value] pairs so client-built and server-echoed selections agree
// regardless of key order, and so two views of the same histogram with
// different selections never collide.
export function histKey(hist_id: string, selection: Selection): string {
  const entries = Object.entries(selection).sort(([a], [b]) => a.localeCompare(b))
  return `${hist_id}:${JSON.stringify(entries)}`
}

// Map from histKey to latest data payload
export const histogramData = writable<Map<string, HistDataPayload>>(new Map())

// Live subscriptions by key, kept so reconnects can re-establish the
// server-side subscription state that is lost when the connection drops.
interface HistSubscription {
  hist_id: string
  selection: Selection
  token: string | null
  rate_limit_hz: number
}
const _subscriptions = new Map<string, HistSubscription>()

function _sendSubscribe(sub: HistSubscription) {
  send({
    type: 'subscribe_hist',
    payload: {
      hist_id: sub.hist_id,
      selection: sub.selection,
      rate_limit_hz: sub.rate_limit_hz,
      ...(sub.token ? { token: sub.token } : {}),
    },
  })
}

onMessage('hist_data', (msg) => {
  if (msg.type !== 'hist_data') return
  histogramData.update((m) => {
    const next = new Map(m)
    next.set(histKey(msg.payload.hist_id, msg.payload.selection), msg.payload)
    return next
  })
})

onOpen(() => {
  for (const sub of _subscriptions.values()) _sendSubscribe(sub)
})

export function subscribeHist(
  hist_id: string,
  selection: Selection,
  token: string | null = null,
  rate_limit_hz = 1.0,
) {
  const sub: HistSubscription = { hist_id, selection, token, rate_limit_hz }
  _subscriptions.set(histKey(hist_id, selection), sub)
  _sendSubscribe(sub)
}

export function unsubscribeHist(hist_id: string, selection: Selection) {
  const key = histKey(hist_id, selection)
  _subscriptions.delete(key)
  send({ type: 'unsubscribe_hist', payload: { hist_id, selection } })
  histogramData.update((m) => {
    const next = new Map(m)
    next.delete(key)
    return next
  })
  // Metadata is per-histogram; drop it only once no view uses the histogram.
  const stillUsed = [..._subscriptions.values()].some((s) => s.hist_id === hist_id)
  if (!stillUsed) {
    histogramMeta.update((m) => {
      const next = new Map(m)
      next.delete(hist_id)
      return next
    })
  }
}
