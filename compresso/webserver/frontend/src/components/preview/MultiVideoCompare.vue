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

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatBytes, formatTime } from 'src/js/formatUtils'
import { useMultiVideoSync } from 'src/composables/useMultiVideoSync'

const props = defineProps({
  candidates: { type: Array, required: true },
  selectedCandidateUuid: { type: String, default: '' },
  winnerEnabled: { type: Boolean, default: true },
  frameRate: { type: Number, default: 24 },
})
defineEmits(['winner-selected'])
const { t } = useI18n()
const videoRefs = ref([])
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const freezeAnalysis = ref(false)
let panning = false
let pointerId = null
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

function setVideoRef(element, index) {
  videoRefs.value[index] = element
}

function statusLabel(status) {
  return status === 'running' ? t('pages.sampleComparison.encoding') : t('pages.sampleComparison.queued')
}

function formatMetric(value, digits) {
  return value == null ? '—' : Number(value).toFixed(digits)
}

function formatPercent(value) {
  const number = Number(value) || 0
  return `${number > 0 ? '+' : ''}${number.toFixed(1)}%`
}

function savingsClass(candidate) {
  if (candidate.status !== 'completed') return ''
  return candidate.size_saved_percent >= 0 ? 'text-positive' : 'text-negative'
}

function step(direction) {
  freezeAnalysis.value = true
  frameStep(direction)
}

function onVideoReady(index) {
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

function onKeydown(event) {
  if (event.target?.closest?.('button, input, [role="slider"]')) return
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

function onZoom(event) {
  zoom.value = Math.min(6, Math.max(1, zoom.value + (event.deltaY > 0 ? -0.25 : 0.25)))
  if (zoom.value === 1) resetZoom()
}

function resetZoom() {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

function startPan(event) {
  if (zoom.value <= 1) return
  panning = true
  pointerId = event.pointerId
  pointerStartX = event.clientX
  pointerStartY = event.clientY
  panStartX = panX.value
  panStartY = panY.value
  event.currentTarget.setPointerCapture?.(pointerId)
}

function movePan(event) {
  if (!panning || event.pointerId !== pointerId) return
  panX.value = panStartX + event.clientX - pointerStartX
  panY.value = panStartY + event.clientY - pointerStartY
}

function endPan(event) {
  if (event.pointerId !== pointerId) return
  panning = false
  pointerId = null
}
</script>

<style scoped>
.comparison-stage {
  --stage-ink: #080b0d;
  --stage-panel: #111619;
  --stage-line: rgba(255, 255, 255, 0.14);
  --stage-amber: #f3b33d;
  overflow: hidden;
  color: #f5f0e6;
  background: var(--stage-ink);
  border: 1px solid var(--stage-line);
  border-radius: 8px;
}

.comparison-stage:focus-visible {
  outline: 2px solid var(--stage-amber);
  outline-offset: 3px;
}

.stage-header,
.transport-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 16px;
  background: #0d1113;
}

.stage-header {
  border-bottom: 1px solid var(--stage-line);
}

.stage-kicker,
.candidate-codec,
.metric-strip span,
.timecode {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.stage-kicker {
  color: var(--stage-amber);
  font-size: 10px;
}

.stage-title {
  margin-top: 2px;
  font-size: 18px;
  font-weight: 650;
}

.candidate-grid {
  display: grid;
  gap: 1px;
  background: var(--stage-line);
}

.candidate-grid--2,
.candidate-grid--4 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.candidate-grid--3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.candidate-cell {
  position: relative;
  min-width: 0;
  background: var(--stage-panel);
}

.candidate-cell--winner::after {
  position: absolute;
  z-index: 2;
  inset: 0;
  border: 2px solid var(--stage-amber);
  content: '';
  pointer-events: none;
}

.video-viewport {
  position: relative;
  overflow: hidden;
  aspect-ratio: 16 / 9;
  background:
    linear-gradient(90deg, transparent 49.8%, rgba(255, 255, 255, 0.035) 50%, transparent 50.2%),
    linear-gradient(0deg, transparent 49.8%, rgba(255, 255, 255, 0.035) 50%, transparent 50.2%), #050607;
  cursor: crosshair;
  touch-action: none;
}

.video-viewport video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  transform-origin: center;
  transition: transform 60ms linear;
}

.cell-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 22px;
  color: #d3d7d8;
  text-align: center;
}

.cell-state--failed {
  color: #ff887d;
}

.cell-state--failed .text-caption {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.cell-progress {
  width: min(240px, 74%);
}

.cell-index {
  position: absolute;
  top: 9px;
  left: 10px;
  padding: 3px 6px;
  color: var(--stage-amber);
  background: rgba(0, 0, 0, 0.72);
  border: 1px solid rgba(243, 179, 61, 0.5);
  border-radius: 3px;
  font:
    600 11px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    Monaco,
    Consolas,
    monospace;
}

.analysis-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(243, 179, 61, 0.2) 1px, transparent 1px),
    linear-gradient(90deg, rgba(243, 179, 61, 0.2) 1px, transparent 1px);
  background-size: 33.333% 33.333%;
}

.candidate-meta {
  padding: 12px 14px 14px;
}

.candidate-name {
  font-size: 15px;
  font-weight: 650;
}

.candidate-codec {
  margin-top: 2px;
  color: #8f9a9e;
  font-size: 10px;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 13px;
}

.metric-strip div {
  min-width: 0;
  padding-top: 8px;
  border-top: 1px solid var(--stage-line);
}

.metric-strip span,
.metric-strip strong {
  display: block;
}

.metric-strip span {
  color: #7e898d;
  font-size: 9px;
}

.metric-strip strong {
  margin-top: 3px;
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.transport-bar {
  border-top: 1px solid var(--stage-line);
}

.transport-buttons {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.transport-slider {
  min-width: 120px;
}

.timecode {
  flex: 0 0 auto;
  color: #aeb7ba;
  font-size: 10px;
  white-space: nowrap;
}

@media (max-width: 980px) {
  .candidate-grid--3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .candidate-grid--3 .candidate-cell:last-child {
    grid-column: 1 / -1;
  }

  .comparison-stage--3 .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .candidate-grid--2,
  .candidate-grid--3,
  .candidate-grid--4 {
    grid-template-columns: 1fr;
  }

  .candidate-grid--3 .candidate-cell:last-child {
    grid-column: auto;
  }

  .stage-header,
  .transport-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .transport-buttons {
    justify-content: center;
  }

  .timecode {
    text-align: center;
  }
}
</style>
