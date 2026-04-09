import { writable } from 'svelte/store'
import type { HistMetaPayload } from '../types/protocol'
import { onMessage } from './websocket'

// Map from hist_id to latest metadata payload
export const histogramMeta = writable<Map<string, HistMetaPayload>>(new Map())

onMessage('hist_meta', (msg) => {
  if (msg.type !== 'hist_meta') return
  histogramMeta.update((m) => {
    const next = new Map(m)
    next.set(msg.payload.hist_id, msg.payload)
    return next
  })
})
