import { describe, expect, it } from 'vitest'
import { parseSystemLogsMessage } from '../systemLogs'

describe('parseSystemLogsMessage', () => {
  it('returns typed system-log data from a valid shared WebSocket envelope', () => {
    const event = new MessageEvent('message', {
      data: JSON.stringify({
        success: true,
        server_id: 'server-1',
        type: 'system_logs',
        data: { system_logs: ['one', 'two'], logs_path: '/tmp/compresso.log' },
      }),
    })

    expect(parseSystemLogsMessage(event)).toEqual({
      system_logs: ['one', 'two'],
      logs_path: '/tmp/compresso.log',
    })
  })

  it('rejects malformed JSON and unrelated stream messages without throwing', () => {
    expect(parseSystemLogsMessage(new MessageEvent('message', { data: '{bad json' }))).toBeNull()
    expect(
      parseSystemLogsMessage(
        new MessageEvent('message', {
          data: JSON.stringify({ success: true, server_id: 'server-1', type: 'pending_tasks', data: {} }),
        }),
      ),
    ).toBeNull()
  })
})
