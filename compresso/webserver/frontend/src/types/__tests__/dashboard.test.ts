import { describe, expect, it } from 'vitest'
import { parseDashboardEnvelope } from '../dashboard'

describe('parseDashboardEnvelope', () => {
  it('accepts the completed task results envelope used by the dashboard', () => {
    const parsed = parseDashboardEnvelope(
      JSON.stringify({
        success: true,
        server_id: 'server-1',
        type: 'completed_tasks',
        data: {
          results: [
            { id: 7, label: 'movie.mkv', finish_time: 123, human_readable_time: '1 minute ago', success: true },
          ],
        },
      }),
    )

    expect(parsed?.success).toBe(true)
    if (parsed?.success && parsed.type === 'completed_tasks') expect(parsed.data.results[0]?.id).toBe(7)
  })

  it('normalizes optional worker telemetry at the browser boundary', () => {
    const parsed = parseDashboardEnvelope(
      JSON.stringify({
        success: true,
        server_id: 'server-1',
        type: 'workers_info',
        data: [{ id: 2, name: 'CPU-Worker-0', idle: false, paused: false, subprocess: { percent: '42.5' } }],
      }),
    )

    expect(parsed?.success).toBe(true)
    if (parsed?.success && parsed.type === 'workers_info') {
      expect(parsed.data[0]?.subprocess.percent).toBe('42.5')
      expect(parsed.data[0]?.worker_log_tail).toEqual([])
    }
  })

  it('rejects malformed task payloads', () => {
    expect(
      parseDashboardEnvelope(
        JSON.stringify({
          success: true,
          server_id: 'server-1',
          type: 'pending_tasks',
          data: { results: [{ id: 'not-a-number' }] },
        }),
      ),
    ).toBeNull()
  })
})

describe('parseDashboardEnvelope regressions', () => {
  it('coerces the stringified worker start_time the backend sends', () => {
    const parsed = parseDashboardEnvelope(
      JSON.stringify({
        success: true,
        server_id: 'server-1',
        type: 'workers_info',
        data: [{ id: 2, name: 'CPU-Worker-0', idle: false, paused: false, start_time: '1712345678.9' }],
      }),
    )

    expect(parsed?.success).toBe(true)
    if (parsed?.success && parsed.type === 'workers_info') {
      expect(parsed.data[0]?.start_time).toBe(1712345678.9)
    }
  })

  it('passes through known stream types the dashboard does not model', () => {
    for (const type of ['frontend_message', 'system_logs']) {
      const parsed = parseDashboardEnvelope(JSON.stringify({ success: true, server_id: 'server-1', type, data: [] }))
      expect(parsed).toEqual({ success: true, server_id: 'server-1', type: 'unhandled' })
    }
  })

  it('still rejects envelopes with unknown stream types', () => {
    expect(
      parseDashboardEnvelope(JSON.stringify({ success: true, server_id: 'server-1', type: 'not_a_stream', data: [] })),
    ).toBeNull()
  })
})
