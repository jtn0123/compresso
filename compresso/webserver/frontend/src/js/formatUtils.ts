/**
 * Shared formatting utility functions.
 */

/**
 * Parse a finite number from a value that may arrive as a number or a
 * numeric string (settings storage and some backend fields round-trip
 * numbers as strings). Returns null when no finite number can be read.
 */
export function parseFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

export function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B'
  const negative = bytes < 0
  bytes = Math.abs(bytes)
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const val = (bytes / Math.pow(k, i)).toFixed(1)
  return (negative ? '-' : '') + val + ' ' + (sizes[i] ?? 'B')
}

export function formatDuration(seconds: number): string {
  if (isNaN(seconds) || seconds <= 0) return '0s'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return h + 'h ' + m + 'm ' + s + 's'
  if (m > 0) return m + 'm ' + s + 's'
  return s + 's'
}

export function formatBitrate(bitsPerSecond: number): string {
  if (!bitsPerSecond || bitsPerSecond === 0) return '0 bps'
  const k = 1000
  const sizes = ['bps', 'Kbps', 'Mbps', 'Gbps']
  const i = Math.floor(Math.log(bitsPerSecond) / Math.log(k))
  const val = (bitsPerSecond / Math.pow(k, i)).toFixed(1)
  return val + ' ' + (sizes[i] ?? 'bps')
}

export function formatTime(seconds: number): string {
  if (isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}
