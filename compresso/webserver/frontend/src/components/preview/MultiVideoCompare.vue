<template>
  <section
    class="comparison-stage"
    :class="`comparison-stage--${candidates.length}`"
    tabindex="0"
    :aria-label="t('pages.sampleComparison.viewerAria')"
    @keydown="onKeydown"
  >
    <header class="stage-header">
      <div>
        <div class="stage-kicker">{{ t('pages.sampleComparison.viewerKicker') }}</div>
        <div class="stage-title">{{ t('pages.sampleComparison.viewerTitle', { count: candidates.length }) }}</div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-badge :color="allReady ? 'positive' : 'grey-9'" text-color="white">
          {{ t('pages.sampleComparison.readyCount', { ready: completedCount, count: candidates.length }) }}
        </q-badge>
        <q-badge color="grey-9" text-color="white">{{ zoom.toFixed(1) }}×</q-badge>
        <q-badge v-if="freezeAnalysis" color="warning" text-color="dark">
          {{ t('pages.sampleComparison.frozen') }}
        </q-badge>
      </div>
    </header>

    <div class="candidate-grid" :class="`candidate-grid--${candidates.length}`">
      <article
        v-for="(candidate, index) in candidates"
        :key="candidate.candidate_uuid"
        class="candidate-cell"
        :class="{
          'candidate-cell--winner': selectedCandidateUuid === candidate.candidate_uuid,
          'candidate-cell--frozen': freezeAnalysis,
        }"
      >
        <div
          class="video-viewport"
          @wheel.prevent="onZoom"
          @pointerdown="startPan"
          @pointermove="movePan"
          @pointerup="endPan"
          @pointercancel="endPan"
        >
          <video
            v-if="candidate.status === 'completed' && candidate.output_url"
            :ref="(element) => setVideoRef(element, index)"
            :src="candidate.output_url"
            :muted="index !== leadIndex"
            playsinline
            preload="metadata"
            :style="videoTransform"
            @loadedmetadata="onVideoReady(index)"
            @timeupdate="onTimeUpdate(index)"
            @ended="pause"
          />

          <div v-else-if="candidate.status === 'failed'" class="cell-state cell-state--failed">
            <q-icon name="error_outline" size="34px" />
            <div class="text-subtitle2 q-mt-sm">{{ t('pages.sampleComparison.encodeFailed') }}</div>
            <div class="text-caption q-mt-xs">{{ candidate.error }}</div>
          </div>

          <div v-else class="cell-state">
            <q-spinner color="warning" size="32px" />
            <div class="text-subtitle2 q-mt-sm">{{ statusLabel(candidate.status) }}</div>
            <q-linear-progress
              :value="(candidate.progress || 0) / 100"
              color="warning"
              track-color="grey-9"
              size="5px"
              class="cell-progress q-mt-md"
            />
            <div class="timecode q-mt-xs">{{ Math.round(candidate.progress || 0) }}%</div>
          </div>

          <div v-if="freezeAnalysis && candidate.status === 'completed'" class="analysis-grid" aria-hidden="true" />
          <div class="cell-index">{{ String(index + 1).padStart(2, '0') }}</div>
        </div>

        <div class="candidate-meta">
          <div class="row items-start no-wrap q-col-gutter-sm">
            <div class="col">
              <div class="candidate-name">{{ candidate.profile_label }}</div>
              <div class="candidate-codec">{{ candidate.encoder }}</div>
            </div>
            <q-btn
              outline
              dense
              color="warning"
              icon="emoji_events"
              :label="
                selectedCandidateUuid === candidate.candidate_uuid
                  ? t('pages.sampleComparison.winner')
                  : t('pages.sampleComparison.pickWinner')
              "
              :disable="candidate.status !== 'completed' || !winnerEnabled"
              @click="$emit('winner-selected', candidate.candidate_uuid)"
            />
          </div>

          <div class="metric-strip">
            <div>
              <span>{{ t('pages.sampleComparison.size') }}</span>
              <strong>{{ candidate.status === 'completed' ? formatBytes(candidate.output_size || 0) : '—' }}</strong>
            </div>
            <div>
              <span>{{ t('pages.sampleComparison.saved') }}</span>
              <strong :class="savingsClass(candidate)">
                {{ candidate.status === 'completed' ? formatPercent(candidate.size_saved_percent) : '—' }}
              </strong>
            </div>
            <div>
              <span>{{ t('pages.sampleComparison.vmaf') }}</span>
              <strong>{{ formatMetric(candidate.vmaf_score, 1) }}</strong>
            </div>
            <div>
              <span>{{ t('pages.sampleComparison.ssim') }}</span>
              <strong>{{ formatMetric(candidate.ssim_score, 3) }}</strong>
            </div>
          </div>
        </div>
      </article>
    </div>

    <footer class="transport-bar">
      <div class="transport-buttons">
        <q-btn flat round icon="skip_previous" :aria-label="t('pages.sampleComparison.seekStart')" @click="seek(0)" />
        <q-btn flat round icon="first_page" :aria-label="t('pages.sampleComparison.previousFrame')" @click="step(-1)" />
        <q-btn
          round
          color="warning"
          text-color="dark"
          :icon="playing ? 'pause' : 'play_arrow'"
          :aria-label="playing ? t('pages.sampleComparison.pause') : t('pages.sampleComparison.play')"
          :disable="completedCount === 0"
          @click="togglePlayback"
        />
        <q-btn flat round icon="last_page" :aria-label="t('pages.sampleComparison.nextFrame')" @click="step(1)" />
        <q-btn
          flat
          round
          :icon="freezeAnalysis ? 'ac_unit' : 'center_focus_strong'"
          :color="freezeAnalysis ? 'warning' : 'white'"
          :aria-label="t('pages.sampleComparison.freezeFrame')"
          @click="toggleFreeze"
        >
          <q-tooltip>{{ t('pages.sampleComparison.freezeFrame') }}</q-tooltip>
        </q-btn>
        <q-btn flat round icon="zoom_out_map" :aria-label="t('pages.sampleComparison.resetZoom')" @click="resetZoom">
          <q-tooltip>{{ t('pages.sampleComparison.resetZoom') }}</q-tooltip>
        </q-btn>
      </div>
      <q-slider
        :model-value="currentTime"
        :min="0"
        :max="duration || 0"
        :step="0.001"
        color="warning"
        class="transport-slider"
        @update:model-value="seek"
      />
      <div class="timecode">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</div>
      <q-tooltip>{{ t('pages.sampleComparison.keyboardControls') }}</q-tooltip>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ComponentPublicInstance, PropType } from 'vue'
import type { ComparisonCandidate } from 'src/types/comparison'
import { useI18n } from 'vue-i18n'
import { formatBytes, formatTime } from 'src/js/formatUtils'
import { useMultiVideoSync } from 'src/composables/useMultiVideoSync'

const props = defineProps({
  candidates: { type: Array as PropType<ComparisonCandidate[]>, required: true },
  selectedCandidateUuid: { type: String, default: '' },
  winnerEnabled: { type: Boolean, default: true },
  frameRate: { type: Number, default: 24 },
})
defineEmits(['winner-selected'])
const { t } = useI18n()
const videoRefs = ref<(HTMLVideoElement | null)[]>([])
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const freezeAnalysis = ref(false)
let panning = false
let pointerId: number | null = null
let pointerStartX = 0
let pointerStartY = 0
let panStartX = 0
let panStartY = 0

const { playing, currentTime, duration, updateDuration, seek, pause, togglePlay, onTimeUpdate, frameStep } =
  useMultiVideoSync(videoRefs, props.frameRate)

const completedCount = computed(() => props.candidates.filter((candidate) => candidate.status === 'completed').length)
const allReady = computed(() => completedCount.value === props.candidates.length)
const leadIndex = computed(() => props.candidates.findIndex((candidate) => candidate.status === 'completed'))
const videoTransform = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
}))

function setVideoRef(element: Element | ComponentPublicInstance | null, index: number) {
  videoRefs.value[index] = element instanceof HTMLVideoElement ? element : null
}

function statusLabel(status: string) {
  return status === 'running' ? t('pages.sampleComparison.encoding') : t('pages.sampleComparison.queued')
}

function formatMetric(value: number | null | undefined, digits: number) {
  return value == null ? '—' : Number(value).toFixed(digits)
}

function formatPercent(value: number | undefined) {
  const number = Number(value) || 0
  return `${number > 0 ? '+' : ''}${number.toFixed(1)}%`
}

function savingsClass(candidate: ComparisonCandidate) {
  if (candidate.status !== 'completed') return ''
  return Number(candidate.size_saved_percent) >= 0 ? 'text-positive' : 'text-negative'
}

function step(direction: number) {
  freezeAnalysis.value = true
  frameStep(direction)
}

function onVideoReady(index: number) {
  updateDuration()
  const video = videoRefs.value[index]
  if (!video) return
  video.currentTime = currentTime.value
  if (playing.value) video.play().catch(() => {})
}

function togglePlayback() {
  if (!playing.value) freezeAnalysis.value = false
  togglePlay()
}

function toggleFreeze() {
  freezeAnalysis.value = !freezeAnalysis.value
  if (freezeAnalysis.value) pause()
}

function onKeydown(event: KeyboardEvent) {
  if (event.target instanceof Element && event.target.closest('button, input, [role="slider"]')) return
  if (event.code === 'Space') {
    event.preventDefault()
    togglePlayback()
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    step(-1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    step(1)
  }
}

function onZoom(event: WheelEvent) {
  zoom.value = Math.min(6, Math.max(1, zoom.value + (event.deltaY > 0 ? -0.25 : 0.25)))
  if (zoom.value === 1) resetZoom()
}

function resetZoom() {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

function startPan(event: PointerEvent) {
  if (zoom.value <= 1) return
  panning = true
  pointerId = event.pointerId
  pointerStartX = event.clientX
  pointerStartY = event.clientY
  panStartX = panX.value
  panStartY = panY.value
  if (event.currentTarget instanceof Element) event.currentTarget.setPointerCapture(pointerId)
}

function movePan(event: PointerEvent) {
  if (!panning || event.pointerId !== pointerId) return
  panX.value = panStartX + event.clientX - pointerStartX
  panY.value = panStartY + event.clientY - pointerStartY
}

function endPan(event: PointerEvent) {
  if (event.pointerId !== pointerId) return
  panning = false
  pointerId = null
}
</script>

<style scoped src="./MultiVideoCompare.css"></style>
