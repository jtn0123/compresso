/**
 * Shared parsing for the backend websocket envelope.
 *
 * Every stream message is `{ success, server_id, type, data }`. This module
 * validates that shell once; each consumer supplies its own payload parsing
 * for the stream types it models and passes the rest through.
 */

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

// Every stream type the backend websocket can emit (websocket.py
// STREAM_POLL_INTERVALS). Consumers model a subset; the rest must be
// passed through silently so shared-socket listeners don't log errors
// for each other's valid traffic.
export const KNOWN_STREAM_TYPES: ReadonlySet<string> = new Set([
  'frontend_message',
  'system_logs',
  'workers_info',
  'pending_tasks',
  'completed_tasks',
  'system_status',
])

export type RawEnvelope = { success: false } | { success: true; server_id: string; type: string; data: unknown }

const parsedMessages = new WeakMap<MessageEvent, RawEnvelope | null>()

/** Parse the envelope shell; payload validation stays with the consumer. */
export function parseRawEnvelope(raw: string): RawEnvelope | null {
  let value: unknown
  try {
    value = JSON.parse(raw) as unknown
  } catch {
    return null
  }
  if (!isRecord(value)) return null
  if (value.success === false) return { success: false }
  if (value.success !== true || typeof value.server_id !== 'string' || typeof value.type !== 'string') return null
  return { success: true, server_id: value.server_id, type: value.type, data: value.data }
}

/** Parse and cache a browser message so every socket listener shares one result. */
export function parseMessageEnvelope(event: MessageEvent): RawEnvelope | null {
  if (parsedMessages.has(event)) return parsedMessages.get(event) ?? null
  const envelope = typeof event.data === 'string' ? parseRawEnvelope(event.data) : null
  parsedMessages.set(event, envelope)
  return envelope
}
