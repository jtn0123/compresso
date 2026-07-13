import { boot } from 'quasar/wrappers'
import axios from 'axios'
import { sharedLinksStore } from 'src/js/sharedLinksStore'
import { getApiToken, promptForApiToken } from 'src/js/apiAuth'

let translate = (key) => key
const CSRF_COOKIE_NAME = 'compresso_csrf_token'
const CSRF_HEADER_NAME = 'X-Compresso-CSRF-Token'

export function getCsrfTokenFromCookie(cookie = globalThis.document?.cookie || '') {
  const prefix = `${CSRF_COOKIE_NAME}=`
  const item = cookie
    .split(';')
    .map((value) => value.trim())
    .find((value) => value.startsWith(prefix))
  if (!item) return ''
  try {
    return decodeURIComponent(item.slice(prefix.length))
  } catch {
    return ''
  }
}

export function isInternalRequestUrl(url) {
  try {
    return new URL(url || '/', window.location.origin).origin === window.location.origin
  } catch {
    return false
  }
}

export function shouldRetryApiAuth(error) {
  const request = error.config
  return Boolean(
    error.response?.status === 401 && request && isInternalRequestUrl(request.url) && !request.__compressoAuthRetried,
  )
}

// Add interceptor to safely attach the proxy header only to internal requests
axios.interceptors.request.use(
  (config) => {
    const target = sharedLinksStore.target
    if (target && target !== 'local' && !config.skipProxy) {
      // Determine if the request is destined for this Compresso instance (Internal)
      if (isInternalRequestUrl(config.url)) {
        config.headers['X-Compresso-Target-Installation'] = target
      }
    }
    const token = getApiToken()
    if (token && isInternalRequestUrl(config.url)) {
      config.headers['X-Compresso-Api-Token'] = token
    }
    const csrfToken = getCsrfTokenFromCookie()
    if (csrfToken && isInternalRequestUrl(config.url)) {
      config.headers[CSRF_HEADER_NAME] = csrfToken
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  },
)

axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    const request = error.config
    if (shouldRetryApiAuth(error)) {
      request.__compressoAuthRetried = true
      const token = promptForApiToken(translate('apiAuth.tokenPrompt'))
      if (token) {
        request.headers['X-Compresso-Api-Token'] = token
        return axios(request)
      }
    }
    return Promise.reject(error)
  },
)

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
  translate = app.config.globalProperties.$t || translate
})

export { axios, api }
