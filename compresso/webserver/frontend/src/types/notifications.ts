import { isRecord } from './envelope'

export type ChannelType = 'discord' | 'slack' | 'webhook'

export interface NotificationChannel {
  id: string
  name: string
  type: ChannelType
  url: string
  headers: Record<string, string> | null
  triggers: string[]
  enabled: boolean
  source: Record<string, unknown>
}

/** Normalize fields the UI manages while retaining the complete source object. */
export function normalizeNotificationChannel(value: unknown): NotificationChannel | null {
  if (!isRecord(value)) return null
  if (
    typeof value.id !== 'string' ||
    (value.type !== 'discord' && value.type !== 'slack' && value.type !== 'webhook') ||
    typeof value.url !== 'string'
  ) {
    return null
  }
  return {
    id: value.id,
    name: typeof value.name === 'string' ? value.name : '',
    type: value.type,
    url: value.url,
    headers: isRecord(value.headers)
      ? Object.fromEntries(
          Object.entries(value.headers).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
        )
      : null,
    triggers: Array.isArray(value.triggers)
      ? value.triggers.filter((trigger): trigger is string => typeof trigger === 'string')
      : [],
    enabled: typeof value.enabled === 'boolean' ? value.enabled : true,
    source: { ...value },
  }
}

/** Merge edited known fields over the untouched backend fields. */
export function serializeNotificationChannel(channel: NotificationChannel): Record<string, unknown> {
  return {
    ...channel.source,
    id: channel.id,
    name: channel.name,
    type: channel.type,
    url: channel.url,
    headers: channel.headers,
    triggers: channel.triggers,
    enabled: channel.enabled,
  }
}
