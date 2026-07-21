import { isRecord, parseMessageEnvelope } from './envelope'

export interface SystemLogsData {
  system_logs: string[]
  logs_path: string
}

/** Parse the system-log payload through the shared per-message envelope cache. */
export function parseSystemLogsMessage(event: MessageEvent): SystemLogsData | null {
  const envelope = parseMessageEnvelope(event)
  if (!envelope?.success || envelope.type !== 'system_logs' || !isRecord(envelope.data)) return null
  if (
    !Array.isArray(envelope.data.system_logs) ||
    !envelope.data.system_logs.every((line) => typeof line === 'string') ||
    typeof envelope.data.logs_path !== 'string'
  ) {
    return null
  }
  return {
    system_logs: envelope.data.system_logs,
    logs_path: envelope.data.logs_path,
  }
}
