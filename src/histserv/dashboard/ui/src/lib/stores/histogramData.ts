import { writable } from 'svelte/store'
import type { HistDataPayload } from '../types/protocol'
import { onMessage, send } from './websocket'
import { histogramMeta } from './histogramMeta'

// Map from hist_id to latest data payload
export const histogramData = writable<Map<string, HistDataPayload>>(new Map())

onMessage('hist_data', (msg) => {
  if (msg.type !== 'hist_data') return
  histogramData.update((m) => {
    const next = new Map(m)
    next.set(msg.payload.hist_id, msg.payload)
    return next
  })
})

export function subscribeHist(
  hist_id: string,
  selection: Record<string, string | number>,
  rate_limit_hz = 1.0,
) {
  send({ type: 'subscribe_hist', payload: { hist_id, selection, rate_limit_hz } })
}

export function unsubscribeHist(hist_id: string, selection: Record<string, string | number>) {
  send({ type: 'unsubscribe_hist', payload: { hist_id, selection } })
  histogramData.update((m) => {
    const next = new Map(m)
    next.delete(hist_id)
    return next
  })
  histogramMeta.update((m) => {
    const next = new Map(m)
    next.delete(hist_id)
    return next
  })
}
