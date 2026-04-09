import { writable } from 'svelte/store'
import type { ClientMessage, ServerMessage } from '../types/protocol'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
const RECONNECT_DELAY_MS = 2000

export type WsStatus = 'connecting' | 'open' | 'closed'

// Exported stores
export const wsStatus = writable<WsStatus>('closed')

// Internal message bus — subscribers register handlers by message type
type MessageHandler = (msg: ServerMessage) => void
const _handlers = new Map<string, Set<MessageHandler>>()

let _ws: WebSocket | null = null
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null

function _connect() {
  wsStatus.set('connecting')
  _ws = new WebSocket(WS_URL)

  _ws.onopen = () => {
    wsStatus.set('open')
    // Re-subscribe to stats stream on reconnect
    send({ type: 'subscribe', payload: { streams: ['stats'] } })
  }

  _ws.onmessage = (event: MessageEvent) => {
    let msg: ServerMessage
    try {
      msg = JSON.parse(event.data as string) as ServerMessage
    } catch {
      return
    }
    const handlers = _handlers.get(msg.type)
    if (handlers) {
      for (const h of handlers) h(msg)
    }
  }

  _ws.onclose = () => {
    wsStatus.set('closed')
    _scheduleReconnect()
  }

  _ws.onerror = () => {
    _ws?.close()
  }
}

function _scheduleReconnect() {
  if (_reconnectTimer !== null) return
  _reconnectTimer = setTimeout(() => {
    _reconnectTimer = null
    _connect()
  }, RECONNECT_DELAY_MS)
}

export function send(msg: ClientMessage) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(msg))
  }
}

export function onMessage(type: ServerMessage['type'], handler: MessageHandler): () => void {
  if (!_handlers.has(type)) _handlers.set(type, new Set())
  _handlers.get(type)!.add(handler)
  return () => _handlers.get(type)?.delete(handler)
}

// Start connection when this module is first imported
_connect()
