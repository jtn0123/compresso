import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useMultiVideoSync } from '../useMultiVideoSync'

function video(duration = 10) {
  return {
    currentTime: 0,
    duration,
    ended: false,
    playbackRate: 1,
    play: vi.fn(() => Promise.resolve()),
    pause: vi.fn(),
  }
}

describe('useMultiVideoSync', () => {
  it('plays, pauses, and seeks every candidate together', async () => {
    const first = video()
    const second = video()
    const refs = ref([first, second])
    const sync = useMultiVideoSync(refs, 25)
    sync.updateDuration()

    await sync.play()
    sync.seek(4.25)
    sync.pause()

    expect(first.play).toHaveBeenCalledOnce()
    expect(second.play).toHaveBeenCalledOnce()
    expect(first.currentTime).toBe(4.25)
    expect(second.currentTime).toBe(4.25)
    expect(first.pause).toHaveBeenCalled()
    expect(sync.playing.value).toBe(false)
  })

  it('frame steps all candidates using the shared frame rate', () => {
    const first = video()
    const second = video()
    const sync = useMultiVideoSync(ref([first, second]), 25)
    sync.updateDuration()
    sync.seek(1)

    sync.frameStep(1)

    expect(sync.currentTime.value).toBeCloseTo(1.04)
    expect(first.currentTime).toBeCloseTo(1.04)
    expect(second.currentTime).toBeCloseTo(1.04)
  })

  it('corrects drift from the lead video', () => {
    const first = video()
    const second = video()
    first.currentTime = 3
    second.currentTime = 2.5
    const sync = useMultiVideoSync(ref([first, second]))

    sync.onTimeUpdate(0)

    expect(second.currentTime).toBe(3)
    expect(sync.currentTime.value).toBe(3)
  })

  it('does not report playback when no candidate is ready', async () => {
    const sync = useMultiVideoSync(ref([]))

    await sync.play()

    expect(sync.playing.value).toBe(false)
  })
})
