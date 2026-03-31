/**
 * Shared formatting utility functions.
 */

export function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const negative = bytes < 0;
  bytes = Math.abs(bytes);
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const val = (bytes / Math.pow(k, i)).toFixed(1);
  return (negative ? '-' : '') + val + ' ' + sizes[i];
}

export function formatDuration(seconds) {
  if (isNaN(seconds) || seconds <= 0) return '0s';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return h + 'h ' + m + 'm ' + s + 's';
  if (m > 0) return m + 'm ' + s + 's';
  return s + 's';
}

export function formatBitrate(bitsPerSecond) {
  if (!bitsPerSecond || bitsPerSecond === 0) return '0 bps';
  const k = 1000;
  const sizes = ['bps', 'Kbps', 'Mbps', 'Gbps'];
  const i = Math.floor(Math.log(bitsPerSecond) / Math.log(k));
  const val = (bitsPerSecond / Math.pow(k, i)).toFixed(1);
  return val + ' ' + sizes[i];
}

export function formatTime(seconds) {
  if (isNaN(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}
