// WebSocket message envelope and discriminated union types

export interface Envelope<T extends string, P> {
  type: T
  ts: number
  payload: P
}

// --- Server → Client ---

export interface StatsPayload {
  histogram_count: number
  histogram_bytes: number
  active_rpcs: number
  version: string
  uptime_seconds: number
  cpu_user: number
  cpu_system: number
  // Per-RPC-method call counts, e.g. { "Init": 2, "Fill": 40, "Snapshot": 1 }
  rpc_calls_total: Record<string, number>
  observed_at: number
}

export interface ErrorPayload {
  message: string
  code: string
}

// ─── UHI axis types (from dense_metadata.axes) ───────────────────────────────
// These match boost-histogram's UHI serialization schema (uhi_schema: 1)

export interface UhiRegularAxis {
  type: 'regular'
  lower: number
  upper: number
  bins: number
  underflow: boolean
  overflow: boolean
  circular: boolean
  metadata?: { name?: string; label?: string; [key: string]: unknown }
}

export interface UhiVariableAxis {
  type: 'variable'
  edges: number[]
  underflow: boolean
  overflow: boolean
  circular: boolean
  metadata?: { name?: string; label?: string; [key: string]: unknown }
}

export interface UhiCategoryStrAxis {
  type: 'category_str'
  categories: string[]
  flow: boolean
  metadata?: { name?: string; label?: string; [key: string]: unknown }
}

export interface UhiCategoryIntAxis {
  type: 'category_int'
  categories: number[]
  flow: boolean
  metadata?: { name?: string; label?: string; [key: string]: unknown }
}

export interface UhiBooleanAxis {
  type: 'boolean'
  metadata?: { name?: string; label?: string; [key: string]: unknown }
}

export type UhiAxis =
  | UhiRegularAxis
  | UhiVariableAxis
  | UhiCategoryStrAxis
  | UhiCategoryIntAxis
  | UhiBooleanAxis

export interface DenseMetadata {
  uhi_schema: number
  axes: UhiAxis[]
  storage: { type: string; [key: string]: unknown }
  metadata: { name?: string; label?: string; [key: string]: unknown }
}

// ─── Chunk axis info (from hist_meta and hist_list) ──────────────────────────

export interface ChunkAxisInfo {
  name: string
  label: string
  // e.g. "category_str" | "category_int"
  type: string
  categories: (string | number)[]
}

// ─── hist_meta payload ────────────────────────────────────────────────────────

export interface HistMetaPayload {
  hist_id: string
  dense_metadata: DenseMetadata
  chunk_axes: ChunkAxisInfo[]
}

// ─── hist_data payload ────────────────────────────────────────────────────────

export interface HistDataPayload {
  hist_id: string
  // The chunk selection used for this slice (empty for unchunked histograms)
  selection: Record<string, string | number>
  // Flat or nested array of bin values including flow bins (underflow + bins + overflow)
  values: number | number[] | number[][]
  // ms-precision timestamp, changes when fills update last_access
  version: number
}

export type ServerMessage =
  | Envelope<'stats', StatsPayload>
  | Envelope<'hist_meta', HistMetaPayload>
  | Envelope<'hist_data', HistDataPayload>
  | Envelope<'error', ErrorPayload>

// --- Client → Server ---

export interface SubscribeHistMsg {
  type: 'subscribe_hist'
  payload: { hist_id: string; selection: Record<string, string | number>; rate_limit_hz?: number }
}

export interface UnsubscribeHistMsg {
  type: 'unsubscribe_hist'
  payload: { hist_id: string; selection: Record<string, string | number> }
}

export interface GetHistMsg {
  type: 'get_hist'
  payload: { hist_id: string; selection: Record<string, string | number> }
}

// Used internally by the websocket store on connect — not exposed in UI
export interface SubscribeStreamsMsg {
  type: 'subscribe'
  payload: { streams: string[] }
}

export type ClientMessage = SubscribeStreamsMsg | SubscribeHistMsg | UnsubscribeHistMsg | GetHistMsg

// ─── Internal rendering type ─────────────────────────────────────────────────
// Derived from UHI metadata; used by d3-histogram.ts (not sent over the wire)

export type RenderAxis =
  | { name: string; label: string; type: 'numeric'; edges: number[] }
  | { name: string; label: string; type: 'categorical'; labels: string[] }
