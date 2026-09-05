import { describe, expect, it } from 'vitest'
import { normalizeNotificationChannel, serializeNotificationChannel } from '../notifications'

describe('notification channel preservation', () => {
  it('keeps unknown backend fields when a managed channel is edited and saved', () => {
    const channel = normalizeNotificationChannel({
      id: 'one',
      name: 'Webhook',
      type: 'webhook',
      url: 'https://example.invalid/hook',
      enabled: true,
      retry_policy: { attempts: 4 },
    })

    expect(channel).not.toBeNull()
    channel!.name = 'Renamed'
    expect(serializeNotificationChannel(channel!)).toEqual({
      id: 'one',
      name: 'Renamed',
      type: 'webhook',
      url: 'https://example.invalid/hook',
      headers: null,
      triggers: [],
      enabled: true,
      retry_policy: { attempts: 4 },
    })
  })

  it('leaves malformed entries unmanaged', () => {
    expect(normalizeNotificationChannel({ id: 'one', type: 'future-channel' })).toBeNull()
  })
})
