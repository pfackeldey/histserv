import { writable } from 'svelte/store'
import type { StatsPayload } from '../types/protocol'
import { onMessage } from './websocket'

export const stats = writable<StatsPayload | null>(null)

// Rolling window for time-series charts (last 60 data points)
const WINDOW = 60
export const statsHistory = writable<StatsPayload[]>([])

onMessage('stats', (msg) => {
  if (msg.type !== 'stats') return
  stats.set(msg.payload)
  statsHistory.update((h) => {
    const next = [...h, msg.payload]
    return next.length > WINDOW ? next.slice(next.length - WINDOW) : next
  })
})
