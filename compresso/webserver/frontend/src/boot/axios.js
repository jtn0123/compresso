import { boot } from 'quasar/wrappers'
import axios from 'axios'
import { sharedLinksStore } from 'src/js/sharedLinksStore'

const MUTATING_METHODS = new Set(['post', 'put', 'patch', 'delete'])

function readCookie(name) {
  const prefix = `${encodeURIComponent(name)}=`
  const cookie = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : ''
}

function isInternalRequest(url = '') {
  const isAbsolute = url.startsWith('http://') || url.startsWith('https://')
  return !isAbsolute || url.startsWith(window.location.origin)
}

export function applyCompressoRequestHeaders(config) {
  config.headers = config.headers || {}
  if (!isInternalRequest(config.url)) {
    return config
  }

  const target = sharedLinksStore.target
  if (target && target !== 'local' && !config.skipProxy) {
    config.headers['X-Compresso-Target-Installation'] = target
  }

  const method = String(config.method || 'get').toLowerCase()
  if (MUTATING_METHODS.has(method)) {
    const csrfToken = readCookie('compresso_csrf_token')
    if (csrfToken) {
      config.headers['X-Compresso-CSRF-Token'] = csrfToken
    }
  }

  return config
}

// Add internal proxy and CSRF headers without leaking them to external requests.
axios.interceptors.request.use(applyCompressoRequestHeaders, (error) => {
  return Promise.reject(error)
})

// Be careful when using SSR for cross-request state pollution
// due to creating a Singleton instance here;
// If any client changes this (global) instance, it might be a
// good idea to move this instance creation inside of the
// "export default () => {}" function below (which runs individually
// for each client)
const api = axios.create({ baseURL: 'https://api.example.com' })

export default boot(({ app }) => {
  // for use inside Vue files (Options API) through this.$axios and this.$api

  app.config.globalProperties.$axios = axios
  // ^ ^ ^ this will allow you to use this.$axios (for Vue Options API form)
  //       so you won't necessarily have to import axios in each vue file

  app.config.globalProperties.$api = api
  // ^ ^ ^ this will allow you to use this.$api (for Vue Options API form)
  //       so you can easily perform requests against your app's API
})

export { axios, api }
