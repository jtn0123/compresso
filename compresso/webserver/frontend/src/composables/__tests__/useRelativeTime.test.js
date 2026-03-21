import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// Mock vue lifecycle hooks since we're not in a component context
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual,
    onUnmounted: vi.fn(),
  }
})

import { useRelativeTime } from '../useRelativeTime'

describe('useRelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-21T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns empty string for null timestamp', () => {
    const ts = ref(null)
    const { relativeTime } = useRelativeTime(ts)
    expect(relativeTime.value).toBe('')
  })

  it('returns "0s ago" for current timestamp', () => {
    const ts = ref(Date.now())
    const { relativeTime } = useRelativeTime(ts)
    expect(relativeTime.value).toBe('0s ago')
  })

  it('returns seconds for recent timestamps', () => {
    const ts = ref(Date.now() - 30_000)
    const { relativeTime } = useRelativeTime(ts)
    expect(relativeTime.value).toBe('30s ago')
  })

  it('returns minutes for timestamps over 60 seconds old', () => {
    const ts = ref(Date.now() - 5 * 60_000)
    const { relativeTime } = useRelativeTime(ts)
    expect(relativeTime.value).toBe('5m ago')
  })

  it('returns hours for timestamps over 3600 seconds old', () => {
    const ts = ref(Date.now() - 2 * 3600_000)
    const { relativeTime } = useRelativeTime(ts)
    expect(relativeTime.value).toBe('2h ago')
  })
})
