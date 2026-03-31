import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('quasar', () => ({ setCssVar: vi.fn(), Notify: { create: vi.fn() } }))
vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: vi.fn(() => 'http://localhost/compresso/api/v2/system/status'),
  showEventToast: vi.fn(),
}))

import axios from 'axios'
import { useSystemStatus } from '../useSystemStatus'

describe('useSystemStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('systemInfo starts as null', () => {
      const { systemInfo } = useSystemStatus()
      expect(systemInfo.value).toBeNull()
    })

    it('liveMetrics starts with all zeros and empty gpus', () => {
      const { liveMetrics } = useSystemStatus()
      expect(liveMetrics.value).toEqual({
        cpu_percent: 0,
        memory_percent: 0,
        memory_used_gb: 0,
        disk_percent: 0,
        disk_used_gb: 0,
        gpus: [],
      })
    })
  })

  describe('fetchSystemInfo', () => {
    it('seeds systemInfo and liveMetrics from a full API response', async () => {
      const mockData = {
        cpu: { percent: 42 },
        memory: { percent: 55, used_gb: 8.1 },
        disk: { percent: 70, used_gb: 120.5 },
        gpus: [{ name: 'GPU0', load: 30 }],
      }
      axios.get.mockResolvedValueOnce({ data: mockData })

      const { systemInfo, liveMetrics, fetchSystemInfo } = useSystemStatus()
      await fetchSystemInfo()

      expect(systemInfo.value).toStrictEqual(mockData)
      expect(liveMetrics.value).toEqual({
        cpu_percent: 42,
        memory_percent: 55,
        memory_used_gb: 8.1,
        disk_percent: 70,
        disk_used_gb: 120.5,
        gpus: [{ name: 'GPU0', load: 30 }],
      })
    })

    it('falls back to 0 for missing cpu/memory/disk/gpus fields', async () => {
      axios.get.mockResolvedValueOnce({ data: {} })

      const { liveMetrics, fetchSystemInfo } = useSystemStatus()
      await fetchSystemInfo()

      expect(liveMetrics.value).toEqual({
        cpu_percent: 0,
        memory_percent: 0,
        memory_used_gb: 0,
        disk_percent: 0,
        disk_used_gb: 0,
        gpus: [],
      })
    })

    it('falls back to 0 for partially missing nested fields', async () => {
      axios.get.mockResolvedValueOnce({
        data: {
          cpu: {},
          memory: { percent: 40 },
          disk: { used_gb: 50 },
        },
      })

      const { liveMetrics, fetchSystemInfo } = useSystemStatus()
      await fetchSystemInfo()

      expect(liveMetrics.value.cpu_percent).toBe(0)
      expect(liveMetrics.value.memory_percent).toBe(40)
      expect(liveMetrics.value.memory_used_gb).toBe(0)
      expect(liveMetrics.value.disk_percent).toBe(0)
      expect(liveMetrics.value.disk_used_gb).toBe(50)
      expect(liveMetrics.value.gpus).toEqual([])
    })

    it('logs the error and keeps existing state when the API call fails', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      axios.get.mockRejectedValueOnce(new Error('Network error'))

      const { systemInfo, liveMetrics, fetchSystemInfo } = useSystemStatus()
      await fetchSystemInfo()

      expect(systemInfo.value).toBeNull()
      expect(liveMetrics.value.cpu_percent).toBe(0)
      expect(consoleSpy).toHaveBeenCalledWith(
        '[SystemStatus]',
        expect.stringContaining('Failed to fetch system status:'),
      )
      consoleSpy.mockRestore()
    })
  })

  describe('startLiveMetrics', () => {
    it('sends the correct JSON command over the WebSocket', () => {
      const ws = { send: vi.fn() }
      const { startLiveMetrics } = useSystemStatus()
      startLiveMetrics(ws)

      expect(ws.send).toHaveBeenCalledOnce()
      expect(ws.send).toHaveBeenCalledWith(
        JSON.stringify({ command: 'start_system_status', params: {} }),
      )
    })

    it('does nothing when ws is null', () => {
      const { startLiveMetrics } = useSystemStatus()
      expect(() => startLiveMetrics(null)).not.toThrow()
    })

    it('does nothing when ws is undefined', () => {
      const { startLiveMetrics } = useSystemStatus()
      expect(() => startLiveMetrics(undefined)).not.toThrow()
    })
  })

  describe('stopLiveMetrics', () => {
    it('sends the correct JSON command over the WebSocket', () => {
      const ws = { send: vi.fn() }
      const { stopLiveMetrics } = useSystemStatus()
      stopLiveMetrics(ws)

      expect(ws.send).toHaveBeenCalledOnce()
      expect(ws.send).toHaveBeenCalledWith(
        JSON.stringify({ command: 'stop_system_status', params: {} }),
      )
    })

    it('does nothing when ws is null', () => {
      const { stopLiveMetrics } = useSystemStatus()
      expect(() => stopLiveMetrics(null)).not.toThrow()
    })

    it('does nothing when ws is undefined', () => {
      const { stopLiveMetrics } = useSystemStatus()
      expect(() => stopLiveMetrics(undefined)).not.toThrow()
    })
  })

  describe('updateLiveMetrics', () => {
    it('updates all fields when a full data object is provided', () => {
      const { liveMetrics, updateLiveMetrics } = useSystemStatus()

      updateLiveMetrics({
        cpu_percent: 80,
        memory_percent: 60,
        memory_used_gb: 12.3,
        disk_percent: 45,
        disk_used_gb: 200,
        gpus: [{ name: 'GPU0', load: 90 }],
      })

      expect(liveMetrics.value).toEqual({
        cpu_percent: 80,
        memory_percent: 60,
        memory_used_gb: 12.3,
        disk_percent: 45,
        disk_used_gb: 200,
        gpus: [{ name: 'GPU0', load: 90 }],
      })
    })

    it('only updates provided fields and preserves the rest (nullish coalescing)', () => {
      const { liveMetrics, updateLiveMetrics } = useSystemStatus()

      // Seed some initial values
      updateLiveMetrics({
        cpu_percent: 50,
        memory_percent: 70,
        memory_used_gb: 8,
        disk_percent: 30,
        disk_used_gb: 100,
        gpus: [],
      })

      // Partial update — only cpu_percent is provided
      updateLiveMetrics({ cpu_percent: 99 })

      expect(liveMetrics.value.cpu_percent).toBe(99)
      expect(liveMetrics.value.memory_percent).toBe(70)
      expect(liveMetrics.value.memory_used_gb).toBe(8)
      expect(liveMetrics.value.disk_percent).toBe(30)
      expect(liveMetrics.value.disk_used_gb).toBe(100)
      expect(liveMetrics.value.gpus).toEqual([])
    })

    it('treats an explicit 0 value as a real update (not falling through ??)', () => {
      const { liveMetrics, updateLiveMetrics } = useSystemStatus()

      // Seed a non-zero value first
      updateLiveMetrics({ cpu_percent: 75, memory_percent: 50 })

      // Explicit 0 should overwrite, not be treated as nullish
      updateLiveMetrics({ cpu_percent: 0 })

      expect(liveMetrics.value.cpu_percent).toBe(0)
      // Unrelated field should remain unchanged
      expect(liveMetrics.value.memory_percent).toBe(50)
    })
  })
})
