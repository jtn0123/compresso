import axios from "axios";
import { ref, reactive } from 'vue'
import { Notify, setCssVar } from 'quasar'
import { createLogger } from 'src/composables/useLogger'

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
function loadToastSettings() {
  try {
    const stored = localStorage.getItem(TOAST_SETTINGS_KEY)
    if (stored) return JSON.parse(stored)
  } catch { /* ignore parse errors */ }
  return { enabled: true, verbosity: 'all' }
}
export const toastSettings = reactive(loadToastSettings())

export function saveToastSettings() {
  try {
    localStorage.setItem(TOAST_SETTINGS_KEY, JSON.stringify({
      enabled: toastSettings.enabled,
      verbosity: toastSettings.verbosity,
    }))
  } catch { /* ignore storage errors */ }
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
export function showEventToast(type, message, options = {}) {
  if (!toastSettings.enabled || toastSettings.verbosity === 'off') return
  // In 'important' mode, only show errors and warnings
  if (toastSettings.verbosity === 'important' && type !== 'error' && type !== 'warning') return

  Notify.create({
    type: undefined,
    color: TOAST_COLOR_MAP[type] || 'info',
    icon: TOAST_ICON_MAP[type] || 'info',
    message: message,
    position: 'bottom-right',
    timeout: 4000,
    actions: [
      { icon: 'close', color: 'white', round: true, dense: true }
    ],
    ...options,
  })
}

let $compresso = {};

export const getCompressoServerUrl = function () {
  if (typeof $compresso.serverUrl === 'undefined') {
    let parser = document.createElement('a');
    parser.href = window.location.href;

    $compresso.serverUrl = parser.protocol + '//' + parser.host;
  }
  return $compresso.serverUrl;
}

export const getCompressoApiUrl = function (api_version, api_endpoint) {
  if (typeof $compresso.apiUrl === 'undefined') {
    let serverUrl = getCompressoServerUrl();

    $compresso.apiUrl = serverUrl + '/compresso/api';
  }
  return $compresso.apiUrl + '/' + api_version + '/' + api_endpoint;
}

export const setTheme = function (mode) {
  if (mode === 'dark') {
    setCssVar('primary', '#22916a');
    setCssVar('secondary', '#d4952a');
    setCssVar('warning', '#d4952a');
    document.body.style.setProperty('--q-card-head', '#1e1e22');
  } else {
    setCssVar('primary', '#1a6b4a');
    setCssVar('secondary', '#e8a525');
    setCssVar('warning', '#e8a525');
    document.body.style.setProperty('--q-card-head', '#f4f6f5');
  }
}

export default {
  $compresso,
  getCompressoVersion() {
    return new Promise((resolve, reject) => {
      if (typeof $compresso.version === 'undefined') {
        axios({
          method: 'get',
          url: getCompressoApiUrl('v2', 'version/read')
        }).then((response) => {
          $compresso.version = response.data.version;
          resolve($compresso.version)
        })
      } else {
        resolve($compresso.version);
      }
    })
  },
  getCompressoSession(options = {}) {
    return new Promise((resolve, reject) => {
      let cacheKey = 'session';
      if (options.skipProxy) {
        cacheKey = 'localSession';
      }

      if (typeof $compresso[cacheKey] === 'undefined') {
        axios({
          method: 'get',
          url: getCompressoApiUrl('v2', 'session/state'),
          ...options
        }).then((response) => {
          $compresso[cacheKey] = {
            created: response.data.created,
            email: response.data.email,
            level: response.data.level,
            name: response.data.name,
            picture_uri: response.data.picture_uri,
            uuid: response.data.uuid,
          }
          resolve($compresso[cacheKey])
        }).catch(() => {
          reject()
        })
      } else {
        resolve($compresso[cacheKey]);
      }
    })
  },
  getCompressoPrivacyPolicy() {
    return new Promise((resolve, reject) => {
      $compresso.docs = (typeof $compresso.docs === 'undefined') ? {} : $compresso.docs
      if (typeof $compresso.docs.privacypolicy === 'undefined') {
        axios({
          method: 'get',
          url: getCompressoApiUrl('v2', 'docs/privacypolicy')
        }).then((response) => {
          $compresso.docs.privacypolicy = response.data.content.join('')
          resolve($compresso.docs.privacypolicy)
        }).catch(() => {
          reject()
        })
      } else {
        resolve($compresso.docs.privacypolicy);
      }
    })
  },
  getCompressoNotifications() {
    if (typeof $compresso.notificationsList === 'undefined') {
      $compresso.notificationsList = [];
    }
    return $compresso.notificationsList;
  },
  updateCompressoNotifications($t) {
    return new Promise((resolve, reject) => {
      $compresso.notificationsList = (typeof $compresso.notificationsList === 'undefined') ? [] : $compresso.notificationsList
      axios({
        method: 'get',
        url: getCompressoApiUrl('v2', 'notifications/read'),
      }).then((response) => {
        // Update success
        let notifications = []
        for (let i = 0; i < response.data.notifications.length; i++) {
          let notification = response.data.notifications[i];
          // Fetch label string from i18n
          let labelStringId = 'notifications.serverNotificationLabels.' + notification.label
          let labelString = $t(labelStringId)
          // If i18n doesn't have this string ID, then revert to just displaying the provided label
          if (labelString === labelStringId) {
            labelString = notification.label;
          }
          // Fetch message string from i18n
          let messageStringId = 'notifications.serverNotificationLabels.' + notification.message
          let messageString = $t(messageStringId)
          // If i18n doesn't have this string ID, then revert to just displaying the provided label
          if (messageString === messageStringId) {
            messageString = notification.message;
          }
          // Set the color of the notification
          let color = 'info';
          if (notification.type === 'error') {
            color = 'negative';
          } else if (notification.type === 'warning') {
            color = 'warning';
          } else if (notification.type === 'success') {
            color = 'positive';
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
        $compresso.notificationsList = notifications;
        notificationsCount.value = notifications.length
        resolve($compresso.notificationsList)
      }).catch(() => {
        log.error("Failed to retrieve server notifications")
        resolve($compresso.notificationsList)
      });
    })
  },
  dismissNotifications($t, uuidList) {
    let queryData = {
      uuid_list: uuidList
    }
    return new Promise((resolve, reject) => {
      $compresso.notificationsList = (typeof $compresso.notificationsList === 'undefined') ? [] : $compresso.notificationsList
      axios({
        method: 'delete',
        url: getCompressoApiUrl('v2', 'notifications/remove'),
        data: queryData,
      }).then((response) => {
        resolve()
      }).catch(() => {
        log.error("Failed to dismiss server notifications")
        resolve()
      });
    })
  },
}
