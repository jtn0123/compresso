import { computed } from 'vue'
import type { Ref } from 'vue'
import type { Translate } from 'src/types/ui'

interface VideoCompareProps {
  sourceSize: number
  encodedSize: number
  vmafScore?: number | null
}

interface VideoCompareMetricsOptions {
  props: VideoCompareProps
  currentTime: Ref<number>
  duration: Ref<number>
  framerate: Ref<number>
  scale: Ref<number>
  translateX: Ref<number>
  translateY: Ref<number>
  playing: Ref<boolean>
  t: Translate
}

export function useVideoCompareMetrics(options: VideoCompareMetricsOptions) {
  const { props, currentTime, duration, framerate, scale, translateX, translateY, playing, t } = options
  const speedOptions = [
    { label: '0.25x', value: 0.25 },
    { label: '0.5x', value: 0.5 },
    { label: '1x', value: 1 },
    { label: '1.5x', value: 1.5 },
    { label: '2x', value: 2 },
  ]

  const shortcutList = computed(() => [
    { key: 'Space', desc: t('components.videoCompare.shortcutPlayPause') },
    { key: '\u2190', desc: t('components.videoCompare.shortcutFrameBackward') },
    { key: '\u2192', desc: t('components.videoCompare.shortcutFrameForward') },
    { key: '+ / =', desc: t('components.videoCompare.shortcutZoomIn') },
    { key: '-', desc: t('components.videoCompare.shortcutZoomOut') },
    { key: '0', desc: t('components.videoCompare.shortcutResetZoom') },
    { key: 'Home', desc: t('components.videoCompare.shortcutSeekStart') },
    { key: 'End', desc: t('components.videoCompare.shortcutSeekEnd') },
  ])

  const savings = computed(() => props.sourceSize - props.encodedSize)
  const savingsPercent = computed(() => {
    if (props.sourceSize <= 0) return 0
    return ((props.sourceSize - props.encodedSize) / props.sourceSize) * 100
  })

  const vmafColor = computed(() => {
    if (props.vmafScore == null) return 'grey'
    if (props.vmafScore >= 90) return 'positive'
    if (props.vmafScore >= 70) return 'warning'
    return 'negative'
  })

  const frameCount = computed(() => Math.floor(duration.value * framerate.value))
  const currentFrame = computed(() => Math.floor(currentTime.value * framerate.value))

  const containerStyle = computed(() => ({
    overflow: 'hidden',
    transform: `scale(${scale.value}) translate(${translateX.value}px, ${translateY.value}px)`,
    transformOrigin: 'center center',
    cursor: scale.value > 1 && !playing.value ? 'crosshair' : scale.value > 1 ? 'grab' : 'default',
  }))

  return {
    speedOptions,
    shortcutList,
    savings,
    savingsPercent,
    vmafColor,
    frameCount,
    currentFrame,
    containerStyle,
  }
}
