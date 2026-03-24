import { describe, it, expect } from 'vitest'
import { formatBytes, formatDuration, formatBitrate, formatTime } from '../formatUtils'

describe('formatBytes', () => {
  it('returns "0 B" for 0', () => {
    expect(formatBytes(0)).toBe('0 B')
  })

  it('returns "0 B" for null', () => {
    expect(formatBytes(null)).toBe('0 B')
  })

  it('returns "0 B" for undefined', () => {
    expect(formatBytes(undefined)).toBe('0 B')
  })

  it('returns "0 B" for NaN', () => {
    expect(formatBytes(NaN)).toBe('0 B')
  })

  it('formats bytes below 1 KB', () => {
    expect(formatBytes(500)).toBe('500.0 B')
  })

  it('formats 1 byte', () => {
    expect(formatBytes(1)).toBe('1.0 B')
  })

  it('formats exactly 1 KB (1024 bytes)', () => {
    expect(formatBytes(1024)).toBe('1.0 KB')
  })

  it('formats kilobytes', () => {
    expect(formatBytes(1536)).toBe('1.5 KB')
  })

  it('formats exactly 1 MB', () => {
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB')
  })

  it('formats megabytes', () => {
    expect(formatBytes(5.5 * 1024 * 1024)).toBe('5.5 MB')
  })

  it('formats exactly 1 GB', () => {
    expect(formatBytes(1024 ** 3)).toBe('1.0 GB')
  })

  it('formats gigabytes', () => {
    expect(formatBytes(2.3 * 1024 ** 3)).toBe('2.3 GB')
  })

  it('formats exactly 1 TB', () => {
    expect(formatBytes(1024 ** 4)).toBe('1.0 TB')
  })

  it('formats terabytes', () => {
    expect(formatBytes(7.8 * 1024 ** 4)).toBe('7.8 TB')
  })

  it('handles negative bytes', () => {
    expect(formatBytes(-1024)).toBe('-1.0 KB')
  })

  it('handles negative megabytes', () => {
    expect(formatBytes(-5 * 1024 * 1024)).toBe('-5.0 MB')
  })

  it('handles very large values', () => {
    expect(formatBytes(10 * 1024 ** 4)).toBe('10.0 TB')
  })

  it('rounds to one decimal place', () => {
    expect(formatBytes(1234567)).toBe('1.2 MB')
  })
})

describe('formatDuration', () => {
  it('returns "0s" for 0', () => {
    expect(formatDuration(0)).toBe('0s')
  })

  it('returns "0s" for negative values', () => {
    expect(formatDuration(-5)).toBe('0s')
  })

  it('returns "0s" for NaN', () => {
    expect(formatDuration(NaN)).toBe('0s')
  })

  it('returns "0s" for undefined', () => {
    expect(formatDuration(undefined)).toBe('0s')
  })

  it('returns "0s" for null', () => {
    expect(formatDuration(null)).toBe('0s')
  })

  it('formats seconds only', () => {
    expect(formatDuration(45)).toBe('45s')
  })

  it('formats 1 second', () => {
    expect(formatDuration(1)).toBe('1s')
  })

  it('formats minutes and seconds', () => {
    expect(formatDuration(125)).toBe('2m 5s')
  })

  it('formats exactly 1 minute', () => {
    expect(formatDuration(60)).toBe('1m 0s')
  })

  it('formats hours, minutes, and seconds', () => {
    expect(formatDuration(3661)).toBe('1h 1m 1s')
  })

  it('formats exactly 1 hour', () => {
    expect(formatDuration(3600)).toBe('1h 0m 0s')
  })

  it('formats multiple hours', () => {
    expect(formatDuration(7384)).toBe('2h 3m 4s')
  })

  it('truncates fractional seconds', () => {
    expect(formatDuration(45.9)).toBe('45s')
  })

  it('handles very large values', () => {
    expect(formatDuration(100000)).toBe('27h 46m 40s')
  })
})

describe('formatBitrate', () => {
  it('returns "0 bps" for 0', () => {
    expect(formatBitrate(0)).toBe('0 bps')
  })

  it('returns "0 bps" for null', () => {
    expect(formatBitrate(null)).toBe('0 bps')
  })

  it('returns "0 bps" for undefined', () => {
    expect(formatBitrate(undefined)).toBe('0 bps')
  })

  it('returns "0 bps" for NaN', () => {
    expect(formatBitrate(NaN)).toBe('0 bps')
  })

  it('formats bits per second', () => {
    expect(formatBitrate(500)).toBe('500.0 bps')
  })

  it('formats 1 bps', () => {
    expect(formatBitrate(1)).toBe('1.0 bps')
  })

  it('formats kilobits per second', () => {
    expect(formatBitrate(1500)).toBe('1.5 Kbps')
  })

  it('formats exactly 1 Kbps (1000 bps)', () => {
    expect(formatBitrate(1000)).toBe('1.0 Kbps')
  })

  it('formats megabits per second', () => {
    expect(formatBitrate(5000000)).toBe('5.0 Mbps')
  })

  it('formats exactly 1 Mbps', () => {
    expect(formatBitrate(1000000)).toBe('1.0 Mbps')
  })

  it('formats gigabits per second', () => {
    expect(formatBitrate(2500000000)).toBe('2.5 Gbps')
  })

  it('formats exactly 1 Gbps', () => {
    expect(formatBitrate(1000000000)).toBe('1.0 Gbps')
  })

  it('rounds to one decimal place', () => {
    expect(formatBitrate(1234567)).toBe('1.2 Mbps')
  })
})

describe('formatTime', () => {
  it('formats zero seconds as "0:00"', () => {
    expect(formatTime(0)).toBe('0:00')
  })

  it('returns "0:00" for NaN', () => {
    expect(formatTime(NaN)).toBe('0:00')
  })

  it('returns "0:00" for undefined', () => {
    expect(formatTime(undefined)).toBe('0:00')
  })

  it('returns "0:00" for null', () => {
    expect(formatTime(null)).toBe('0:00')
  })

  it('pads single-digit seconds with a leading zero', () => {
    expect(formatTime(5)).toBe('0:05')
  })

  it('formats seconds without padding when >= 10', () => {
    expect(formatTime(30)).toBe('0:30')
  })

  it('formats minutes and seconds', () => {
    expect(formatTime(125)).toBe('2:05')
  })

  it('formats exactly 1 minute', () => {
    expect(formatTime(60)).toBe('1:00')
  })

  it('formats large values', () => {
    expect(formatTime(3661)).toBe('61:01')
  })

  it('truncates fractional seconds', () => {
    expect(formatTime(65.9)).toBe('1:05')
  })

  it('handles negative seconds', () => {
    // Math.floor(-30/60) = -1 and (-30 % 60) = -30, producing "-1:-30"
    expect(formatTime(-30)).toBe('-1:-30')
  })
})
