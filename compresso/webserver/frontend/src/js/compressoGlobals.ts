import axios, { type AxiosRequestConfig } from 'axios'
import { ref, reactive } from 'vue'
import { Notify, LocalStorage, type QNotifyCreateOptions, type QNotifyUpdateOptions } from 'quasar'
import { createLogger } from 'src/composables/useLogger'
import { applyTheme, isPaletteName, type ThemeMode } from 'src/js/compressoTheme'
import type { ApiSchema } from 'src/types/contracts'
import type { Translate } from 'src/types/ui'

const log = createLogger('Globals')

/**
 * Reactive notification count shared across all consumers.
 * Updated automatically when notifications are fetched or dismissed.
 */
export const notificationsCount = ref(0)

/**
 * Toast settings for real-time event notifications.
 * Persisted to localStorage.
 */
const TOAST_SETTINGS_KEY = 'compresso-toast-settings'
type ToastType = 'success' | 'error' | 'warning' | 'info'
type ToastVerbosity = 'all' | 'important' | 'off'

interface ToastSettings {
  enabled: boolean
  verbosity: ToastVerbosity
}

export interface DisplayNotification {
  uuid: string
  icon: string
  navigation: Record<string, unknown>
  label: string
  message: string
  color: string
}

export interface CompressoSocket extends WebSocket {
  __compressoBoundListenerKeys?: Set<string>
}

export interface RegisteredWebSocketListener {
  type: keyof WebSocketEventMap
  callback: EventListener
}

interface CompressoCache {
  serverUrl?: string
  apiUrl?: string
  version?: string
  session?: ApiSchema<'SessionStateSuccess'>
  localSession?: ApiSchema<'SessionStateSuccess'>
  docs?: { privacypolicy?: string }
  notificationsList?: DisplayNotification[]
}

export interface CompressoGlobalsService {
  $compresso: CompressoCache
  ws?: CompressoSocket | null
  websocketEventListeners?: Record<string, RegisteredWebSocketListener>
  frontendMessage?: Record<string, (options?: QNotifyUpdateOptions) => void>
  getCompressoVersion(): Promise<string>
  getCompressoSession(options?: AxiosRequestConfig): Promise<ApiSchema<'SessionStateSuccess'>>
  getCompressoPrivacyPolicy(): Promise<string>
  getCompressoNotifications(): DisplayNotification[]
  updateCompressoNotifications(t: Translate): Promise<DisplayNotification[]>
  dismissNotifications(t: Translate, uuidList: string[]): Promise<void>
  loginGetAppAuthCode(t: Translate, onSuccess: (data: ApiSchema<'SessionAuthCode'>) => void): Promise<void>
}

function isToastSettings(value: unknown): value is ToastSettings {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Partial<ToastSettings>
  return (
    typeof candidate.enabled === 'boolean' &&
    (candidate.verbosity === 'all' || candidate.verbosity === 'important' || candidate.verbosity === 'off')
  )
}

function loadToastSettings(): ToastSettings {
  try {
    const stored = LocalStorage.getItem(TOAST_SETTINGS_KEY)
    if (isToastSettings(stored)) return stored
  } catch {
    /* ignore parse errors */
  }
  return { enabled: true, verbosity: 'all' }
}
export const toastSettings = reactive<ToastSettings>(loadToastSettings())

export function saveToastSettings(): void {
  try {
    LocalStorage.set(TOAST_SETTINGS_KEY, {
      enabled: toastSettings.enabled,
      verbosity: toastSettings.verbosity,
    })
  } catch {
    /* ignore storage errors */
  }
}

const TOAST_ICON_MAP = {
  success: 'check_circle',
  error: 'error',
  warning: 'warning',
  info: 'info',
}
const TOAST_COLOR_MAP = {
  success: 'positive',
  error: 'negative',
  warning: 'warning',
  info: 'info',
}

/**
 * Show a toast notification for real-time events.
 *
 * @param {'success'|'error'|'warning'|'info'} type
 * @param {string} message
 * @param {object} [options] - Additional Quasar Notify options
 */
export function showEventToast(type: ToastType, message: string, options: Partial<QNotifyCreateOptions> = {}): void {
  if (!toastSettings.enabled || toastSettings.verbosity === 'off') return
  // In 'important' mode, only show errors and warnings
  if (toastSettings.verbosity === 'important' && type !== 'error' && type !== 'warning') return

  Notify.create({
    color: TOAST_COLOR_MAP[type],
    icon: TOAST_ICON_MAP[type],
    message,
    position: 'bottom-right',
    timeout: 4000,
    actions: [{ icon: 'close', color: 'white', round: true, dense: true }],
    ...options,
  })
}

const $compresso: CompressoCache = {}

export const getCompressoServerUrl = function (): string {
  if (typeof $compresso.serverUrl === 'undefined') {
    const parser = document.createElement('a')
    parser.href = window.location.href

    $compresso.serverUrl = parser.protocol + '//' + parser.host
  }
  return $compresso.serverUrl
}

export const getCompressoApiUrl = function (apiVersion: string, apiEndpoint: string): string {
  if (typeof $compresso.apiUrl === 'undefined') {
    const serverUrl = getCompressoServerUrl()

    $compresso.apiUrl = serverUrl + '/compresso/api'
  }
  return $compresso.apiUrl + '/' + apiVersion + '/' + apiEndpoint
}

export const setTheme = function (mode: ThemeMode): void {
  const storedPalette = LocalStorage.getItem('palette')
  const palette = isPaletteName(storedPalette) ? storedPalette : 'forest'
  applyTheme(mode, palette)
}

const compressoGlobals: CompressoGlobalsService = {
  $compresso,
  getCompressoVersion() {
    return new Promise<string>((resolve, reject) => {
      if (typeof $compresso.version === 'undefined') {
        axios<ApiSchema<'VersionReadSuccess'>>({
          method: 'get',
          url: getCompressoApiUrl('v2', 'version/read'),
        })
          .then((response) => {
            $compresso.version = response.data.version
            resolve($compresso.version)
          })
          .catch((err) => {
            // Without this catch the promise would hang forever on
            // network errors; mirrors how the sibling getters reject.
            reject(err)
          })
      } else {
        resolve($compresso.version)
      }
    })
  },
  getCompressoSession(options: AxiosRequestConfig = {}) {
    return new Promise<ApiSchema<'SessionStateSuccess'>>((resolve, reject) => {
      let cacheKey: 'session' | 'localSession' = 'session'
      if (options.skipProxy) {
        cacheKey = 'localSession'
      }

      const cachedSession = $compresso[cacheKey]
      if (typeof cachedSession === 'undefined') {
        axios<ApiSchema<'SessionStateSuccess'>>({
          method: 'get',
          url: getCompressoApiUrl('v2', 'session/state'),
          ...options,
        })
          .then((response) => {
            const session = response.data
            $compresso[cacheKey] = session
            resolve(session)
          })
          .catch(() => {
            reject()
          })
      } else {
        resolve(cachedSession)
      }
    })
  },
  getCompressoPrivacyPolicy() {
    return new Promise<string>((resolve, reject) => {
      const docs = ($compresso.docs ??= {})
      if (typeof docs.privacypolicy === 'undefined') {
        axios<ApiSchema<'DocumentContentSuccess'>>({
          method: 'get',
          url: getCompressoApiUrl('v2', 'docs/privacypolicy'),
        })
          .then((response) => {
            docs.privacypolicy = response.data.content.join('')
            resolve(docs.privacypolicy)
          })
          .catch(() => {
            reject()
          })
      } else {
        resolve(docs.privacypolicy)
      }
    })
  },
  getCompressoNotifications() {
    if (typeof $compresso.notificationsList === 'undefined') {
      $compresso.notificationsList = []
    }
    return $compresso.notificationsList
  },
  updateCompressoNotifications($t: Translate) {
    return new Promise<DisplayNotification[]>((resolve) => {
      $compresso.notificationsList =
        typeof $compresso.notificationsList === 'undefined' ? [] : $compresso.notificationsList
      axios<ApiSchema<'RequestNotificationsData'>>({
        method: 'get',
        url: getCompressoApiUrl('v2', 'notifications/read'),
      })
        .then((response) => {
          // Update success
          const notifications: DisplayNotification[] = []
          for (let i = 0; i < response.data.notifications.length; i++) {
            const notification = response.data.notifications[i]
            if (!notification) continue
            // Fetch label string from i18n
            const labelStringId = 'notifications.serverNotificationLabels.' + notification.label
            let labelString = $t(labelStringId)
            // If i18n doesn't have this string ID, then revert to just displaying the provided label
            if (labelString === labelStringId) {
              labelString = notification.label
            }
            // Fetch message string from i18n
            const messageStringId = 'notifications.serverNotificationLabels.' + notification.message
            let messageString = $t(messageStringId)
            // If i18n doesn't have this string ID, then revert to just displaying the provided label
            if (messageString === messageStringId) {
              messageString = notification.message
            }
            // Set the color of the notification
            let color = 'info'
            if (notification.type === 'error') {
              color = 'negative'
            } else if (notification.type === 'warning') {
              color = 'warning'
            } else if (notification.type === 'success') {
              color = 'positive'
            }
            // Add notification to list
            notifications[notifications.length] = {
              uuid: notification.uuid,
              icon: notification.icon,
              navigation: notification.navigation,
              label: labelString,
              message: messageString,
              color: color,
            }
          }
          $compresso.notificationsList = notifications
          notificationsCount.value = notifications.length
          resolve(notifications)
        })
        .catch(() => {
          log.error('Failed to retrieve server notifications')
          resolve($compresso.notificationsList ?? [])
        })
    })
  },
  dismissNotifications(_t: Translate, uuidList: string[]) {
    const queryData = {
      uuid_list: uuidList,
    }
    return new Promise<void>((resolve) => {
      $compresso.notificationsList =
        typeof $compresso.notificationsList === 'undefined' ? [] : $compresso.notificationsList
      axios({
        method: 'delete',
        url: getCompressoApiUrl('v2', 'notifications/remove'),
        data: queryData,
      })
        .then(() => {
          resolve()
        })
        .catch(() => {
          log.error('Failed to dismiss server notifications')
          resolve()
        })
    })
  },
  async loginGetAppAuthCode(t: Translate, onSuccess: (data: ApiSchema<'SessionAuthCode'>) => void): Promise<void> {
    try {
      const response = await axios.get<ApiSchema<'SessionAuthCode'>>(
        getCompressoApiUrl('v2', 'session/get_app_auth_code'),
      )
      onSuccess(response.data)
    } catch (error) {
      log.error('Failed to initiate application authentication', error)
      showEventToast('error', t('components.loginDialog.sessionStateFailed'))
    }
  },
}

export default compressoGlobals
