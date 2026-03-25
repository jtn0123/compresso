import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

/**
 * Global keyboard shortcut composable.
 *
 * Navigation uses a two-key chord: press `g` then a second key within 800ms.
 * Single keys trigger actions (e.g. `?` toggles the shortcut help dialog).
 *
 * Shortcuts are suppressed when focus is inside an input, textarea, select,
 * or content-editable element and when Ctrl/Meta/Alt modifiers are held.
 */
export function useKeyboardShortcuts() {
  const router = useRouter()
  const showHelp = ref(false)
  let pendingPrefix = null
  let prefixTimer = null

  const shortcuts = {
    // Navigation (g + key chord)
    'g+d': () => router.push('/ui/dashboard'),
    'g+c': () => router.push('/ui/compression'),
    'g+a': () => router.push('/ui/approval'),
    'g+h': () => router.push('/ui/health'),
    'g+p': () => router.push('/ui/preview'),
    'g+s': () => router.push('/ui/settings-library'),
    'g+w': () => router.push('/ui/settings-workers'),
    // Actions
    '?': () => { showHelp.value = !showHelp.value },
  }

  function handleKeydown(e) {
    // Don't capture when typing in inputs/textareas
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return
    if (e.target.isContentEditable) return
    // Don't capture when modifiers are held (except for Shift which is needed for ?)
    if (e.ctrlKey || e.metaKey || e.altKey) return

    const key = e.key.toLowerCase()

    // Escape always closes the help dialog
    if (e.key === 'Escape') {
      if (showHelp.value) {
        showHelp.value = false
        e.preventDefault()
      }
      return
    }

    if (pendingPrefix) {
      const combo = pendingPrefix + '+' + key
      clearTimeout(prefixTimer)
      pendingPrefix = null
      if (shortcuts[combo]) {
        e.preventDefault()
        shortcuts[combo]()
        return
      }
    }

    if (key === 'g') {
      pendingPrefix = 'g'
      prefixTimer = setTimeout(() => { pendingPrefix = null }, 800)
      return
    }

    // Check for the ? key (Shift+/ on most keyboards, but e.key === '?')
    const actionKey = e.key
    if (shortcuts[actionKey]) {
      e.preventDefault()
      shortcuts[actionKey]()
    }
  }

  onMounted(() => document.addEventListener('keydown', handleKeydown))
  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeydown)
    if (prefixTimer) clearTimeout(prefixTimer)
  })

  return { showHelp, shortcuts }
}
