import { showEventToast } from 'src/js/compressoGlobals'

const isProduction = process.env.NODE_ENV === 'production'

/**
 * Create a logger with a tagged prefix.
 * Works in plain JS files (no Vue context needed).
 *
 * @param {string} tag - Component/module name for log prefix
 * @returns {{ debug: Function, info: Function, warn: Function, error: Function }}
 */
export interface LogOptions {
  toast?: boolean
}

export interface Logger {
  debug(...args: unknown[]): void
  info(...args: unknown[]): void
  warn(message: unknown, details?: unknown): void
  error(message: unknown, details?: unknown): void
}

function requestsToast(details: unknown): boolean {
  return typeof details === 'object' && details !== null && 'toast' in details && details.toast === true
}

export function createLogger(tag: string): Logger {
  const prefix = `[${tag}]`

  return {
    debug(...args: unknown[]) {
      if (!isProduction) {
        console.debug(prefix, ...args)
      }
    },
    info(...args: unknown[]) {
      if (!isProduction) {
        console.info(prefix, ...args)
      }
    },
    warn(message: unknown, details?: unknown) {
      console.warn(prefix, message)
      if (requestsToast(details)) {
        showEventToast('warning', typeof message === 'string' ? message : String(message))
      }
    },
    error(message: unknown, details?: unknown) {
      console.error(prefix, message)
      if (requestsToast(details)) {
        showEventToast('error', typeof message === 'string' ? message : String(message))
      }
    },
  }
}

/**
 * Vue composable alias for createLogger.
 * Use in Vue components' setup() function.
 */
export function useLogger(tag: string): Logger {
  return createLogger(tag)
}
