import { showEventToast } from 'src/js/compressoGlobals'

const isProduction = process.env.NODE_ENV === 'production'

/**
 * Create a logger with a tagged prefix.
 * Works in plain JS files (no Vue context needed).
 *
 * @param {string} tag - Component/module name for log prefix
 * @returns {{ debug: Function, info: Function, warn: Function, error: Function }}
 */
export function createLogger(tag) {
  const prefix = `[${tag}]`

  return {
    debug(...args) {
      if (!isProduction) {
        console.debug(prefix, ...args)
      }
    },
    info(...args) {
      if (!isProduction) {
        console.info(prefix, ...args)
      }
    },
    warn(message, options = {}) {
      console.warn(prefix, message)
      if (options.toast) {
        showEventToast('warning', typeof message === 'string' ? message : String(message))
      }
    },
    error(message, options = {}) {
      console.error(prefix, message)
      if (options.toast) {
        showEventToast('error', typeof message === 'string' ? message : String(message))
      }
    },
  }
}

/**
 * Vue composable alias for createLogger.
 * Use in Vue components' setup() function.
 */
export function useLogger(tag) {
  return createLogger(tag)
}
