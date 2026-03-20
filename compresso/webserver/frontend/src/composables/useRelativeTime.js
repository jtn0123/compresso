import { ref, watch, onUnmounted } from 'vue'

/**
 * Returns a reactive string like "5s ago", "2m ago", "1h ago"
 * that updates every second based on the provided timestamp ref.
 *
 * @param {import('vue').Ref<number|null>} timestampRef - A ref holding a Date.now()-style timestamp
 * @returns {{ relativeTime: import('vue').Ref<string> }}
 */
export function useRelativeTime(timestampRef) {
  const relativeTime = ref('')

  function update() {
    if (!timestampRef.value) {
      relativeTime.value = ''
      return
    }
    const diff = Math.max(0, Math.floor((Date.now() - timestampRef.value) / 1000))
    if (diff < 60) {
      relativeTime.value = diff + 's ago'
    } else if (diff < 3600) {
      relativeTime.value = Math.floor(diff / 60) + 'm ago'
    } else {
      relativeTime.value = Math.floor(diff / 3600) + 'h ago'
    }
  }

  update()
  const interval = setInterval(update, 1000)

  watch(timestampRef, update)

  onUnmounted(() => {
    clearInterval(interval)
  })

  return { relativeTime }
}
