import { Notify } from 'quasar'
import { ref } from 'vue'
import $compresso, { showEventToast, type CompressoSocket, type RegisteredWebSocketListener } from './compressoGlobals'
import { createLogger } from 'src/composables/useLogger'
import { getWebsocketProtocols } from 'src/js/apiAuth'
import { KNOWN_STREAM_TYPES } from 'src/types/dashboard'
import type { QNotifyUpdateOptions } from 'quasar'
import type { Translate } from 'src/types/ui'

const log = createLogger('WebSocket')

type FrontendMessageType = 'error' | 'warning' | 'success' | 'info' | 'status'

interface FrontendPushMessage {
  id: string
  type: FrontendMessageType
  code: string
  message: string
  timeout: number
}

// Mirrors websocket.py async_completed_tasks_info: the stream only carries
// id/label/success (plus finish_time/human_readable_time, unused here).
interface CompletedTaskMessage {
  id: number
  label?: string
  success: boolean
}

type IncomingEnvelope =
  | { success: false }
  | { success: true; server_id: string; type: 'unhandled' }
  | { success: true; server_id: string; type: 'frontend_message'; data: FrontendPushMessage[] }
  | { success: true; server_id: string; type: 'completed_tasks'; data: { results: CompletedTaskMessage[] } }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isFrontendPushMessage(value: unknown): value is FrontendPushMessage {
  if (!isRecord(value)) return false
  return (
    typeof value.id === 'string' &&
    (value.type === 'error' ||
      value.type === 'warning' ||
      value.type === 'success' ||
      value.type === 'info' ||
      value.type === 'status') &&
    typeof value.code === 'string' &&
    typeof value.message === 'string' &&
    typeof value.timeout === 'number'
  )
}

function isCompletedTaskMessage(value: unknown): value is CompletedTaskMessage {
  return (
    isRecord(value) &&
    typeof value.id === 'number' &&
    typeof value.success === 'boolean' &&
    (value.label === undefined || typeof value.label === 'string')
  )
}

export function parseIncomingEnvelope(raw: string): IncomingEnvelope | null {
  let value: unknown
  try {
    value = JSON.parse(raw) as unknown
  } catch {
    return null
  }
  if (!isRecord(value) || value.success !== true)
    return isRecord(value) && value.success === false ? { success: false } : null
  if (typeof value.server_id !== 'string' || typeof value.type !== 'string') return null
  if (value.type === 'frontend_message') {
    if (!Array.isArray(value.data) || !value.data.every(isFrontendPushMessage)) return null
    return { success: true, server_id: value.server_id, type: value.type, data: value.data }
  }
  if (value.type === 'completed_tasks') {
    if (
      !isRecord(value.data) ||
      !Array.isArray(value.data.results) ||
      !value.data.results.every(isCompletedTaskMessage)
    ) {
      return null
    }
    return { success: true, server_id: value.server_id, type: value.type, data: { results: value.data.results } }
  }
  // Valid envelope of a stream this handler does not model (e.g. workers_info,
  // pending_tasks): pass through so the server_id restart check still sees it
  // and no error is logged for another listener's valid traffic.
  if (KNOWN_STREAM_TYPES.has(value.type)) {
    return { success: true, server_id: value.server_id, type: 'unhandled' }
  }
  return null
}

export function escapeHtml(str: string | null | undefined): string {
  if (!str) return ''
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

/**
 * Reactive WebSocket connection state shared across all consumers.
 * Values: 'connected', 'connecting', 'disconnected'
 */
export const wsConnectionState = ref<'connected' | 'connecting' | 'disconnected'>('disconnected')

/**
 * Function for handle default WS connection to the Compresso service.
 * This will return a WS instance which can be expanded upon with
 * additional requests depending on the page's requirements.
 *
 * @param $t
 * @returns {{init: (function(): *), close: close}}
 * @constructor
 */
export const CompressoWebsocketHandler = function ($t: Translate) {
  let clearConnectionWarning: ((options?: QNotifyUpdateOptions) => void) | null = null
  let autoReconnectSocket = true
  let connectionTimer: ReturnType<typeof setTimeout> | null = null
  let serverId: string | null = null
  let connectionCheckInterval: ReturnType<typeof setInterval> | null = null
  const ownedListenerKeys = new Set<string>()

  // Track seen completed task IDs to detect new completions and avoid re-toasting
  const seenCompletedIds = new Set<number>()
  let connectionEstablishedAt = 0

  function listenerRegistry(): Record<string, RegisteredWebSocketListener> {
    $compresso.websocketEventListeners ??= {}
    return $compresso.websocketEventListeners
  }

  function socketBindingKeys(socket: CompressoSocket): Set<string> {
    socket.__compressoBoundListenerKeys ??= new Set<string>()
    return socket.__compressoBoundListenerKeys
  }

  function bindRegisteredListeners(socket: CompressoSocket | null | undefined): void {
    if (!socket) {
      return
    }
    const bindingKeys = socketBindingKeys(socket)

    Object.entries(listenerRegistry()).forEach(([key, listener]) => {
      if (bindingKeys.has(key)) {
        return
      }
      socket.addEventListener(listener.type, listener.callback)
      bindingKeys.add(key)
    })
  }

  function removeRegisteredListener(key: string): void {
    const registry = listenerRegistry()
    const listener = registry[key]
    if (!listener) {
      return
    }

    if (typeof $compresso.ws !== 'undefined' && $compresso.ws !== null) {
      $compresso.ws.removeEventListener(listener.type, listener.callback)
      socketBindingKeys($compresso.ws).delete(key)
    }

    delete registry[key]
    ownedListenerKeys.delete(key)
  }

  function removeOwnedListeners(): void {
    Array.from(ownedListenerKeys).forEach((key) => {
      removeRegisteredListener(key)
    })
  }

  /**
   * Init the websocket to the compresso backend server
   *
   * @returns {null|WebSocket|*}
   */
  const initWebsocket = function (): CompressoSocket | null {
    function showWebsocketConnectionWarning(): void {
      // Ensure the websocket is actually missing
      if (typeof $compresso.ws !== 'undefined' && $compresso.ws !== null) {
        return
      }
      if (clearConnectionWarning === null) {
        log.debug('Display websocket disconnect warning')
        clearConnectionWarning = Notify.create({
          timeout: 0,
          spinner: true,
          color: 'warning',
          position: 'top',
          message: $t('notifications.backendConnectionWarning'),
          icon: 'report_problem',
        })
        if (connectionCheckInterval) clearInterval(connectionCheckInterval)
        connectionCheckInterval = setInterval(() => {
          if (typeof $compresso.ws !== 'undefined' && $compresso.ws !== null) {
            if ($compresso.ws.readyState === WebSocket.OPEN) {
              log.debug('Websocket has reconnected. Clearing warning.')
              clearConnectionWarning?.()
              clearConnectionWarning = null
              if (connectionCheckInterval !== null) clearInterval(connectionCheckInterval)
              connectionCheckInterval = null
            }
          }
        }, 500)
      }
    }

    function openWS(): void {
      if (typeof $compresso.ws === 'undefined' || $compresso.ws === null) {
        // Build WS path
        const loc = window.location
        let new_uri: string
        if (loc.protocol === 'https:') {
          new_uri = 'wss:'
        } else {
          new_uri = 'ws:'
        }
        new_uri += '//' + loc.host + '/compresso/websocket'

        // Check for Shared Link Target
        const target = localStorage.getItem('compresso-installation-target')
        if (target && target !== 'local') {
          new_uri += '?target_id=' + encodeURIComponent(target)
        }

        // Open WS connection
        wsConnectionState.value = 'connecting'
        $compresso.ws = new WebSocket(new_uri, getWebsocketProtocols()) as CompressoSocket
        bindRegisteredListeners($compresso.ws)
      }
    }

    function reconnectWS(): void {
      if (connectionTimer) {
        clearTimeout(connectionTimer)
      }
      // Set ws as null so that it needs to be recreated
      $compresso.ws = null
      wsConnectionState.value = 'disconnected'
      connectionTimer = setTimeout(() => {
        log.debug('Attempting reconnect to Compresso server...')
        wsConnectionState.value = 'connecting'
        initWebsocket()
      }, 4000)
    }

    function frontendMessages(): Record<string, (options?: QNotifyUpdateOptions) => void> {
      $compresso.frontendMessage ??= {}
      return $compresso.frontendMessage
    }

    function dismissMessages(messageId: string): void {
      const messages = frontendMessages()
      if (typeof messages[messageId] === 'function') {
        messages[messageId]()
        if (typeof $compresso.ws !== 'undefined' && $compresso.ws !== null) {
          $compresso.ws.send(JSON.stringify({ command: 'dismiss_message', params: { message_id: messageId } }))
        }
      }
      if (typeof messages[messageId] !== 'undefined') {
        delete messages[messageId]
      }
    }

    function displayStatus(
      translate: Translate,
      messageId: string,
      type: FrontendMessageType,
      code: string,
      message: string,
      _timeout: number,
    ): void {
      // Create new status message
      // Fetch message string from i18n
      const notificationStringId = 'notifications.serverMessages.' + code
      let notificationString = translate(notificationStringId)
      // If i18n doesnt have this string ID, then revert to default
      if (notificationString === notificationStringId) {
        notificationString = translate('notifications.serverMessages.defaults.' + type)
      }
      // If the message is not empty, concatenate it to the end of the notification string
      if (message) {
        notificationString = notificationString + '<br>' + escapeHtml(message)
      } else {
        // Check if a preset message is available
        const messageStringId = 'notifications.serverMessages.' + code + 'Message'
        const messageString = translate(messageStringId)
        // If i18n doesnt have this string ID, then revert to default
        if (messageString !== messageStringId) {
          message = translate('notifications.serverMessages.' + code + 'Message')
          // Concatenate it to the end
          notificationString = notificationString + '<br>' + message
        }
      }

      notificationString =
        '' + '<span style="display:block;min-height:50px;white-space:pre;">' + notificationString + '</span>'

      const messages = frontendMessages()
      if (!(messageId in messages)) {
        messages[messageId] = Notify.create({
          group: false,
          type: 'ongoing',
          position: 'bottom-left',
          message: notificationString,
          html: true,
        })
      } else {
        // Update the current status message
        messages[messageId]?.({
          message: notificationString,
          html: true,
        })
      }
    }

    function displayNotice(
      translate: Translate,
      messageId: string,
      type: FrontendMessageType,
      code: string,
      message: string,
      timeout: number,
    ): void {
      const messages = frontendMessages()
      if (!(messageId in messages)) {
        // Fetch message string from i18n
        const notificationStringId = 'notifications.serverMessages.' + code
        let notificationString = translate(notificationStringId)
        // If i18n doesnt have this string ID, then revert to default
        if (notificationString === notificationStringId) {
          notificationString = translate('notifications.serverMessages.defaults.' + type)
        }
        // If the message is not empty, concatenate it to the end of the notification string
        if (message) {
          notificationString = notificationString + ' - ' + escapeHtml(message)
        }

        // Format notification based on message type
        let color = 'info'
        let icon = 'announcement'
        if (type === 'error') {
          color = 'negative'
          icon = 'error'
        } else if (type === 'warning') {
          color = 'warning'
          icon = 'warning'
        } else if (type === 'success') {
          color = 'positive'
          icon = 'thumb_up'
        }

        messages[messageId] = Notify.create({
          timeout: timeout,
          color: color,
          position: 'bottom-right',
          message: notificationString,
          icon: icon,
          actions: [
            {
              icon: 'close',
              color: 'white',
              handler: () => {
                dismissMessages(messageId)
              },
            },
          ],
        })
      }
    }

    function displayMessages(data: FrontendPushMessage[]): void {
      const currentIds: string[] = []
      for (const item of data) {
        const { id: messageId, type, code, message, timeout } = item
        if (type === 'status') {
          displayStatus($t, messageId, type, code, message, timeout)
        } else {
          displayNotice($t, messageId, type, code, message, timeout)
        }
        currentIds.push(messageId)
      }
      for (const messageId in frontendMessages()) {
        if (!currentIds.includes(messageId)) {
          dismissMessages(messageId)
        }
      }
    }

    // Ensure the websocket is open
    if (typeof $compresso.ws === 'undefined' || $compresso.ws === null) {
      log.debug('Starting connection to websocket server')
      // Open WS connection
      openWS()

      // Add event listener to request frontend messages from server
      addWebsocketEventListener('open', 'start_frontend_messages', function () {
        if (connectionTimer !== null) clearTimeout(connectionTimer)
        connectionTimer = null
        wsConnectionState.value = 'connected'
        connectionEstablishedAt = Date.now()
        if (clearConnectionWarning !== null) {
          clearConnectionWarning()
          clearConnectionWarning = null
        }
        if (connectionCheckInterval) {
          clearInterval(connectionCheckInterval)
          connectionCheckInterval = null
        }
        $compresso.ws?.send(JSON.stringify({ command: 'start_frontend_messages', params: {} }))
      })

      // Add event listener to handle frontend messages from server
      addWebsocketEventListener('message', 'handle_frontend_messages', function (evt) {
        if (typeof evt.data === 'string') {
          const jsonData = parseIncomingEnvelope(evt.data)
          if (jsonData?.success) {
            // Ensure the server is still running the same instance...
            if (serverId === null) {
              serverId = jsonData.server_id
            } else {
              if (jsonData.server_id !== serverId) {
                // Reload the whole page. Some things may have changed
                log.debug('Compresso server has restarted. Reloading page...')
                location.reload()
              }
            }
            // Parse data type and update the dashboard
            switch (jsonData.type) {
              case 'frontend_message':
                displayMessages(jsonData.data)
                break
              case 'completed_tasks':
                if (jsonData.type === 'completed_tasks') {
                  const connectionAge = Date.now() - connectionEstablishedAt
                  for (const task of jsonData.data.results) {
                    if (task.id && !seenCompletedIds.has(task.id)) {
                      seenCompletedIds.add(task.id)
                      // Only toast if connected for >5s (skip initial load batch)
                      if (connectionAge > 5000) {
                        const filename = task.label || $t('toasts.unknownFile')
                        if (task.success) {
                          showEventToast('success', $t('toasts.taskCompleted') + ': ' + filename)
                        } else {
                          // Retry notifications are delivered via frontend_message (not completed_tasks)
                          showEventToast('error', $t('toasts.taskFailed') + ': ' + filename)
                        }
                      }
                    }
                  }
                  // Cap set size to prevent unbounded memory growth
                  if (seenCompletedIds.size > 500) {
                    seenCompletedIds.clear()
                  }
                }
                break
            }
          } else if (jsonData?.success === false) {
            log.error('WebSocket Error: Received contained errors - ' + evt.data)
          } else {
            log.error('WebSocket Error: Received an invalid payload')
          }
        } else {
          log.error('WebSocket Error: Received data was not a string - ' + evt.data)
        }
      })

      // Add event listener to handle an error in the websocket
      addWebsocketEventListener('error', 'websocket_error', function (evt) {
        log.error('WebSocket Error: ' + String(evt))
        // Set a timeout before displaying disconnect warning.
        // Sometimes we get a disconnect just from a slow connection.
        setTimeout(() => {
          // Display error
          showWebsocketConnectionWarning()
        }, 5000)
      })

      // Add event listener to auto-reconnect the websocket if the socket closes
      addWebsocketEventListener('close', 'websocket_close', function () {
        if (autoReconnectSocket) {
          reconnectWS()
        }
      })
    }

    return $compresso.ws ?? null
  }

  /**
   * Add an event listener to the websocket.
   * This allows us to ensure that event listeners are not duplicated.
   *
   * @param type
   * @param key
   * @param callback
   */
  const addWebsocketEventListener = function <Type extends keyof WebSocketEventMap>(
    type: Type,
    key: string,
    callback: (event: WebSocketEventMap[Type]) => void,
  ): void {
    const registry = listenerRegistry()
    const eventListener = callback as EventListener
    const existing = registry[key]
    if (existing && existing.type === type && existing.callback === eventListener) {
      ownedListenerKeys.add(key)
      bindRegisteredListeners($compresso.ws)
      return
    }
    if (existing) {
      removeRegisteredListener(key)
    }
    registry[key] = { type, callback: eventListener }
    ownedListenerKeys.add(key)
    bindRegisteredListeners($compresso.ws)
  }

  /**
   * Close the websocket without triggering a reconnect
   */
  const closeWebsocket = function (): void {
    autoReconnectSocket = false
    removeOwnedListeners()
    if (typeof $compresso.ws !== 'undefined' && $compresso.ws !== null) {
      log.debug('Closing connection to websocket server')
      // Clear any connection check interval
      if (connectionCheckInterval) {
        clearInterval(connectionCheckInterval)
        connectionCheckInterval = null
      }
      if (connectionTimer) {
        clearTimeout(connectionTimer)
        connectionTimer = null
      }
      // Close WS connection
      $compresso.ws.close()
      $compresso.ws = null
      wsConnectionState.value = 'disconnected'
    }
  }

  return {
    serverId,
    init: function () {
      return initWebsocket()
    },
    close: function () {
      closeWebsocket()
    },
    addEventListener: addWebsocketEventListener,
    removeEventListener: removeRegisteredListener,
  }
}

export default {
  CompressoWebsocketHandler,
}
