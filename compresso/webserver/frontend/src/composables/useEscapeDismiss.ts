import { onUnmounted } from 'vue'
import { useQuasar } from 'quasar'

/**
 * Escape-to-dismiss for viewports where Quasar does not provide it.
 *
 * Quasar's `addEscapeKey` is a no-op unless `Platform.is.desktop`:
 *
 *     export function addEscapeKey (fn) {
 *       if (client.is.desktop) { handlers.push(fn) ... }
 *     }
 *
 * so on any touch-capable viewport no QDialog reacts to Escape. That is
 * defensible for a phone with no keyboard, but it strands keyboard users on a
 * touchscreen laptop, a tablet with a keyboard case, and a desktop browser in
 * responsive mode — all of which report as touch platforms.
 *
 * This registers a fallback only where Quasar declined to, so desktop keeps
 * Quasar's own handling and nothing fires twice. Dialogs form a stack and only
 * the top one dismisses, matching how Quasar behaves when several are open.
 */

const dismissStack: Array<() => void> = []
let listening = false

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  const top = dismissStack[dismissStack.length - 1]
  if (top === undefined) return
  event.preventDefault()
  top()
}

function startListening(): void {
  if (listening) return
  document.addEventListener('keydown', onKeydown)
  listening = true
}

function stopListening(): void {
  if (!listening || dismissStack.length > 0) return
  document.removeEventListener('keydown', onKeydown)
  listening = false
}

export function useEscapeDismiss(dismiss: () => void) {
  const $q = useQuasar()
  let registered: (() => void) | null = null

  /** Quasar already handles Escape on desktop; only fill the gap elsewhere. */
  const quasarHandlesEscape = () => $q.platform.is.desktop === true

  function activate(): void {
    if (quasarHandlesEscape() || registered !== null) return
    registered = dismiss
    dismissStack.push(registered)
    startListening()
  }

  function deactivate(): void {
    if (registered === null) return
    const index = dismissStack.lastIndexOf(registered)
    if (index !== -1) dismissStack.splice(index, 1)
    registered = null
    stopListening()
  }

  onUnmounted(deactivate)

  return { activate, deactivate }
}
