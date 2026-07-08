import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useVideoCompareMetrics } from '../useVideoCompareMetrics'

function makeMetrics(overrides = {}) {
  return useVideoCompareMetrics({
    props: {
      sourceSize: 1000,
      encodedSize: 700,
      vmafScore: 95,
      ...overrides.props,
    },
    currentTime: ref(overrides.currentTime ?? 2),
    duration: ref(overrides.duration ?? 10),
    framerate: ref(overrides.framerate ?? 24),
    scale: ref(overrides.scale ?? 1),
    translateX: ref(overrides.translateX ?? 0),
    translateY: ref(overrides.translateY ?? 0),
    playing: ref(overrides.playing ?? false),
    t: (key) => key,
  })
}

describe('useVideoCompareMetrics', () => {
  it('calculates savings and quality badge state', () => {
    const metrics = makeMetrics()

    expect(metrics.savings.value).toBe(300)
    expect(metrics.savingsPercent.value).toBe(30)
    expect(metrics.vmafColor.value).toBe('positive')
  })

  it('derives frame counters and zoom cursor style', () => {
    const metrics = makeMetrics({ scale: 2 })

    expect(metrics.frameCount.value).toBe(240)
    expect(metrics.currentFrame.value).toBe(48)
    expect(metrics.containerStyle.value.cursor).toBe('crosshair')
  })
})
