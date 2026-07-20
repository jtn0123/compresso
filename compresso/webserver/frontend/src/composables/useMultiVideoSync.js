import { computed, ref } from 'vue'

export function useMultiVideoSync(videoRefs, frameRate = 24) {
  const playing = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const syncing = ref(false)

  const readyVideos = computed(() => videoRefs.value.filter((video) => video && Number.isFinite(video.duration)))

  function updateDuration() {
    const durations = readyVideos.value.map((video) => video.duration).filter((value) => value > 0)
    duration.value = durations.length ? Math.min(...durations) : 0
  }

  function seek(time) {
    const requested = Number(time)
    const safeTime = Number.isFinite(requested) ? requested : 0
    const bounded = Math.max(0, duration.value > 0 ? Math.min(safeTime, duration.value) : safeTime)
    syncing.value = true
    for (const video of readyVideos.value) {
      video.currentTime = bounded
    }
    currentTime.value = bounded
    requestAnimationFrame(() => {
      syncing.value = false
    })
  }

  async function play() {
    if (!readyVideos.value.length) return
    const results = await Promise.allSettled(readyVideos.value.map((video) => video.play()))
    playing.value = results.some((result) => result.status === 'fulfilled')
  }

  function pause() {
    for (const video of readyVideos.value) video.pause()
    playing.value = false
  }

  function togglePlay() {
    return playing.value ? pause() : play()
  }

  function onTimeUpdate(index) {
    if (syncing.value) return
    const leader = videoRefs.value[index]
    if (!leader) return
    currentTime.value = leader.currentTime || 0
    for (const video of readyVideos.value) {
      if (video !== leader && Math.abs(video.currentTime - currentTime.value) > 0.08) {
        video.currentTime = currentTime.value
      }
    }
    if (leader.ended) playing.value = false
  }

  function frameStep(direction) {
    pause()
    const step = 1 / Math.max(1, Number(frameRate) || 24)
    seek(currentTime.value + step * direction)
  }

  return {
    playing,
    currentTime,
    duration,
    updateDuration,
    seek,
    play,
    pause,
    togglePlay,
    onTimeUpdate,
    frameStep,
  }
}
