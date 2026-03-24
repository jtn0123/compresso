import { describe, it, expect, vi } from 'vitest'

vi.mock('quasar', () => ({
  date: {
    formatDate: (d, fmt) => {
      const pad = (n) => String(n).padStart(2, '0')
      const Y = d.getFullYear()
      const M = pad(d.getMonth() + 1)
      const D = pad(d.getDate())
      const h = pad(d.getHours())
      const m = pad(d.getMinutes())
      const s = pad(d.getSeconds())
      return `${Y}-${M}-${D} ${h}:${m}:${s}`
    },
  },
}))

import dateTools from '../dateTools'

describe('printSecondsAsDuration', () => {
  it('returns empty string for 0', () => {
    expect(dateTools.printSecondsAsDuration(0)).toBe('')
  })

  it('returns "1 second" for 1 second', () => {
    expect(dateTools.printSecondsAsDuration(1)).toBe('1 second')
  })

  it('returns plural seconds', () => {
    expect(dateTools.printSecondsAsDuration(45)).toBe('45 seconds')
  })

  it('returns "1 minute" singular', () => {
    expect(dateTools.printSecondsAsDuration(60)).toBe('1 minute')
  })

  it('returns plural minutes with seconds', () => {
    expect(dateTools.printSecondsAsDuration(125)).toBe('2 minutes, 5 seconds')
  })

  it('returns "1 hour" singular', () => {
    expect(dateTools.printSecondsAsDuration(3600)).toBe('1 hour')
  })

  it('returns plural hours', () => {
    expect(dateTools.printSecondsAsDuration(7200)).toBe('2 hours')
  })

  it('returns hours, minutes, and seconds combined', () => {
    expect(dateTools.printSecondsAsDuration(3661)).toBe('1 hour, 1 minute, 1 second')
  })

  it('returns plural hours, minutes, and seconds', () => {
    expect(dateTools.printSecondsAsDuration(7384)).toBe('2 hours, 3 minutes, 4 seconds')
  })

  it('returns "1 day" singular', () => {
    expect(dateTools.printSecondsAsDuration(86400)).toBe('1 day')
  })

  it('returns plural days', () => {
    expect(dateTools.printSecondsAsDuration(172800)).toBe('2 days')
  })

  it('returns days, hours, minutes, and seconds', () => {
    expect(dateTools.printSecondsAsDuration(90061)).toBe('1 day, 1 hour, 1 minute, 1 second')
  })

  it('handles string input', () => {
    expect(dateTools.printSecondsAsDuration('125')).toBe('2 minutes, 5 seconds')
  })

  it('handles minutes without remaining seconds', () => {
    expect(dateTools.printSecondsAsDuration(120)).toBe('2 minutes')
  })

  it('handles hours without remaining minutes or seconds', () => {
    expect(dateTools.printSecondsAsDuration(7200)).toBe('2 hours')
  })

  it('handles NaN input', () => {
    expect(dateTools.printSecondsAsDuration(NaN)).toBe('')
  })

  it('handles null input', () => {
    expect(dateTools.printSecondsAsDuration(null)).toBe('')
  })

  it('handles undefined input', () => {
    expect(dateTools.printSecondsAsDuration(undefined)).toBe('')
  })

  it('handles negative input', () => {
    expect(dateTools.printSecondsAsDuration(-100)).toBe('')
  })

  it('handles very large values', () => {
    const result = dateTools.printSecondsAsDuration(100000)
    expect(result).toBe('1 day, 3 hours, 46 minutes, 40 seconds')
  })
})

describe('printDateTimeString', () => {
  it('formats a unix timestamp', () => {
    // 2024-01-15 12:30:45 UTC => depends on local TZ, but the mock
    // just calls our stub which uses local Date methods.
    const ts = 1705318245
    const result = dateTools.printDateTimeString(ts)
    // Verify the format matches YYYY-MM-DD HH:mm:ss
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
  })

  it('formats epoch 0', () => {
    const result = dateTools.printDateTimeString(0)
    // Uses local timezone via Date, so just verify the format
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
  })

  it('returns a string in YYYY-MM-DD HH:mm:ss format', () => {
    const result = dateTools.printDateTimeString(1609459200) // 2021-01-01 00:00:00 UTC
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
  })
})
