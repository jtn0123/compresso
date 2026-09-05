import { describe, expect, it, vi } from 'vitest'
import { parseMessageEnvelope } from '../envelope'

describe('parseMessageEnvelope', () => {
  it('parses the same browser message only once for all listeners', () => {
    const parse = vi.spyOn(JSON, 'parse')
    const event = new MessageEvent('message', {
      data: JSON.stringify({ success: true, server_id: 'server-1', type: 'pending_tasks', data: [] }),
    })

    const first = parseMessageEnvelope(event)
    const second = parseMessageEnvelope(event)

    expect(second).toBe(first)
    expect(parse).toHaveBeenCalledTimes(1)
    parse.mockRestore()
  })
})
