<template>
  <div class="video-compare" tabindex="0" ref="rootRef">
    <!-- Mode Toggle -->
    <div class="row items-center q-mb-md q-gutter-sm">
      <q-btn-toggle
        v-model="viewMode"
        toggle-color="primary"
        :options="[
          { label: 'Side by Side', value: 'side-by-side' },
          { label: 'Slider', value: 'slider' },
        ]"
        dense
        flat
      />
      <q-space />
      <!-- Quality Badges -->
      <q-badge v-if="vmafScore != null" :color="vmafColor" class="q-pa-sm text-body2">
        VMAF: {{ vmafScore.toFixed(1) }}
      </q-badge>
      <q-badge v-else class="q-pa-sm text-body2" color="grey">VMAF: N/A</q-badge>
      <q-badge v-if="ssimScore != null" class="q-pa-sm text-body2" color="info">
        SSIM: {{ (ssimScore * 100).toFixed(1) }}%
      </q-badge>
      <q-badge v-else class="q-pa-sm text-body2" color="grey">SSIM: N/A</q-badge>
      <q-badge
        class="q-pa-sm text-body2"
        :color="encodedByPipeline ? 'positive' : 'grey'"
      >
        {{ encodedByPipeline ? 'Plugin Pipeline' : 'Default Encode' }}
      </q-badge>
    </div>

    <!-- Side-by-Side Mode -->
    <div v-if="viewMode === 'side-by-side'" class="row q-col-gutter-md">
      <div class="col-12 col-md-6">
        <q-card>
          <q-card-section class="q-pb-none">
            <div class="text-subtitle1">
              Original
              <q-badge class="q-ml-sm">{{ formatBytes(sourceSize) }}</q-badge>
              <q-badge class="q-ml-sm" color="grey">{{ sourceCodec }}</q-badge>
              <q-badge v-if="sourceResolution" class="q-ml-sm" color="grey-7">{{ sourceResolution }}</q-badge>
            </div>
          </q-card-section>
          <q-card-section>
            <div
              class="video-container"
              :style="containerStyle"
              @wheel.prevent="onZoom"
              @mousedown="onPanStart"
              @touchstart="onTouchStart"
              @touchmove="onTouchMove"
              @touchend="onTouchEnd"
            >
              <!-- A/B Label Overlay -->
              <div class="ab-label ab-label-source">A &mdash; Original</div>
              <!-- Video Error Overlay -->
              <div v-if="videoError" class="video-error-overlay">{{ videoError }}</div>
              <video
                ref="sourceVideoRef"
                :src="sourceUrl"
                class="full-width"
                :playbackRate="playbackSpeed"
                @loadedmetadata="onSourceLoaded"
                @timeupdate="onSourceTimeUpdate"
                @error="onVideoError"
              />
              <!-- Mini-Map -->
              <canvas
                v-if="showMiniMap"
                ref="sourceMiniMapRef"
                class="mini-map"
                width="120"
                height="80"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12 col-md-6">
        <q-card>
          <q-card-section class="q-pb-none">
            <div class="text-subtitle1">
              Encoded
              <q-badge class="q-ml-sm" color="positive">{{ formatBytes(encodedSize) }}</q-badge>
              <q-badge class="q-ml-sm" color="grey">{{ encodedCodec }}</q-badge>
              <q-badge v-if="encodedResolution" class="q-ml-sm" color="grey-7">{{ encodedResolution }}</q-badge>
            </div>
          </q-card-section>
          <q-card-section>
            <div
              class="video-container"
              :style="containerStyle"
              @wheel.prevent="onZoom"
              @mousedown="onPanStart"
              @touchstart="onTouchStart"
              @touchmove="onTouchMove"
              @touchend="onTouchEnd"
            >
              <!-- A/B Label Overlay -->
              <div class="ab-label ab-label-encoded">B &mdash; Encoded</div>
              <video
                ref="encodedVideoRef"
                :src="encodedUrl"
                class="full-width"
                :playbackRate="playbackSpeed"
                @loadedmetadata="onEncodedLoaded"
                @error="onVideoError"
              />
              <!-- Mini-Map -->
              <canvas
                v-if="showMiniMap"
                ref="encodedMiniMapRef"
                class="mini-map"
                width="120"
                height="80"
              />
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <!-- Slider Mode -->
    <div v-if="viewMode === 'slider'" class="slider-compare-container">
      <q-card>
        <q-card-section class="q-pb-none">
          <div class="row">
            <div class="col text-subtitle1">
              Original
              <q-badge class="q-ml-sm">{{ formatBytes(sourceSize) }}</q-badge>
              <q-badge v-if="sourceResolution" class="q-ml-sm" color="grey-7">{{ sourceResolution }}</q-badge>
            </div>
            <div class="col text-right text-subtitle1">
              Encoded
              <q-badge class="q-ml-sm" color="positive">{{ formatBytes(encodedSize) }}</q-badge>
              <q-badge v-if="encodedResolution" class="q-ml-sm" color="grey-7">{{ encodedResolution }}</q-badge>
            </div>
          </div>
        </q-card-section>
        <q-card-section>
          <div
            class="slider-viewport"
            ref="sliderViewportRef"
            :style="containerStyle"
            @wheel.prevent="onZoom"
            @mousedown="onPanStart"
            @touchstart="onTouchStart"
            @touchmove="onTouchMove"
            @touchend="onTouchEnd"
          >
            <video
              ref="encodedVideoRef"
              :src="encodedUrl"
              class="slider-video"
              :playbackRate="playbackSpeed"
              @loadedmetadata="onEncodedLoaded"
              @error="onVideoError"
            />
            <div class="slider-source-clip" :style="{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }">
              <video
                ref="sourceVideoRef"
                :src="sourceUrl"
                class="slider-video"
                :playbackRate="playbackSpeed"
                @loadedmetadata="onSourceLoaded"
                @timeupdate="onSourceTimeUpdate"
                @error="onVideoError"
              />
            </div>
            <div
              class="slider-divider"
              :style="{ left: sliderPos + '%' }"
              @mousedown.stop="onSliderDragStart"
              @touchstart.stop="onSliderTouchStart"
              @keydown="onSliderKeyDown"
              tabindex="0"
              role="slider"
              :aria-valuenow="Math.round(sliderPos)"
              aria-valuemin="0"
              aria-valuemax="100"
              aria-label="Comparison slider"
            >
              <!-- Slider A/B labels -->
              <div class="slider-ab-label slider-ab-label-a">A</div>
              <div class="slider-handle"></div>
              <div class="slider-ab-label slider-ab-label-b">B</div>
            </div>
          </div>
        </q-card-section>
      </q-card>
    </div>

    <!-- Size Comparison -->
    <q-card class="q-mt-md" v-if="sourceSize > 0 && encodedSize > 0">
      <q-card-section>
        <div class="text-center">
          <span class="text-h6">
            {{ formatBytes(sourceSize) }} &rarr; {{ formatBytes(encodedSize) }}
          </span>
          <q-badge
            class="q-ml-md text-h6"
            :color="savings > 0 ? 'positive' : 'negative'"
          >
            {{ savings > 0 ? '-' : '+' }}{{ Math.abs(savingsPercent).toFixed(1) }}%
          </q-badge>
          <div class="text-caption q-mt-xs">
            {{ savings > 0 ? 'Saved' : 'Increased by' }} {{ formatBytes(Math.abs(savings)) }}
          </div>
        </div>
      </q-card-section>
    </q-card>

    <!-- Shared Controls -->
    <q-card class="q-mt-md">
      <q-card-section>
        <div class="row items-center q-gutter-sm">
          <q-btn flat round icon="skip_previous" @click="seekToStart" aria-label="Skip to start" />
          <q-btn flat round icon="fast_rewind" @click="framePrev" aria-label="Previous frame" />
          <q-btn flat round :icon="playing ? 'pause' : 'play_arrow'" @click="togglePlay" :aria-label="playing ? 'Pause' : 'Play'" />
          <q-btn flat round icon="fast_forward" @click="frameNext" aria-label="Next frame" />
          <q-btn flat round icon="skip_next" @click="seekToEnd" aria-label="Skip to end" />
          <q-separator vertical class="q-mx-xs" />
          <q-select
            v-model="playbackSpeed"
            :options="speedOptions"
            label="Speed"
            dense
            outlined
            emit-value
            map-options
            style="width: 90px"
            @update:model-value="onSpeedChange"
          />
          <q-btn flat round :icon="looping ? 'repeat_one' : 'repeat'" :color="looping ? 'primary' : ''" @click="looping = !looping" :aria-label="looping ? 'Disable loop' : 'Enable loop'" />
          <!-- Snapshot Button -->
          <q-btn
            flat
            round
            icon="photo_camera"
            :disable="playing"
            @click="takeSnapshot"
          >
            <q-tooltip>Take snapshot (paused only)</q-tooltip>
          </q-btn>
          <!-- Keyboard Shortcuts Button -->
          <q-btn flat round icon="keyboard">
            <q-menu>
              <q-list dense style="min-width: 220px">
                <q-item-label header>Keyboard Shortcuts</q-item-label>
                <q-item v-for="sc in shortcutList" :key="sc.key">
                  <q-item-section side>
                    <q-badge color="grey-8" text-color="white">{{ sc.key }}</q-badge>
                  </q-item-section>
                  <q-item-section>{{ sc.desc }}</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
            <q-tooltip>Keyboard shortcuts</q-tooltip>
          </q-btn>
          <q-slider
            v-model="currentTime"
            :min="0"
            :max="duration"
            :step="0.001"
            class="col"
            @update:model-value="onSeek"
          />
          <span class="text-caption" style="white-space: nowrap">
            {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
            <span v-if="frameCount > 0" class="q-ml-sm">F:{{ currentFrame }}</span>
          </span>
        </div>
        <div class="row items-center q-mt-xs q-gutter-sm" v-if="scale > 1">
          <q-badge color="info">Zoom: {{ scale.toFixed(1) }}x</q-badge>
          <q-btn flat dense size="sm" label="Reset Zoom" @click="resetZoom" />
        </div>
      </q-card-section>
    </q-card>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useQuasar } from 'quasar';
import { formatBytes, formatTime } from 'src/js/formatUtils';

export default {
  name: 'VideoCompare',
  props: {
    sourceUrl: { type: String, required: true },
    encodedUrl: { type: String, required: true },
    sourceSize: { type: Number, default: 0 },
    encodedSize: { type: Number, default: 0 },
    sourceCodec: { type: String, default: '' },
    encodedCodec: { type: String, default: '' },
    vmafScore: { type: Number, default: null },
    ssimScore: { type: Number, default: null },
    encodedByPipeline: { type: Boolean, default: false },
    framerate: { type: Number, default: 24 },
  },
  setup(props) {
    const $q = useQuasar();
    const rootRef = ref(null);
    const videoError = ref('');
    const sourceVideoRef = ref(null);
    const encodedVideoRef = ref(null);
    const sliderViewportRef = ref(null);
    const sourceMiniMapRef = ref(null);
    const encodedMiniMapRef = ref(null);
    const playing = ref(false);
    const currentTime = ref(0);
    const duration = ref(0);
    const framerate = ref(props.framerate);
    const syncing = ref(false);
    const viewMode = ref('side-by-side');
    const sliderPos = ref(50);
    const playbackSpeed = ref(1);
    const looping = ref(false);
    const scale = ref(1);
    const translateX = ref(0);
    const translateY = ref(0);
    const sourceResolution = ref('');
    const encodedResolution = ref('');
    let isPanning = false;
    let panStartX = 0;
    let panStartY = 0;
    let panStartTranslateX = 0;
    let panStartTranslateY = 0;
    let isSliderDragging = false;

    const speedOptions = [
      { label: '0.25x', value: 0.25 },
      { label: '0.5x', value: 0.5 },
      { label: '1x', value: 1 },
      { label: '1.5x', value: 1.5 },
      { label: '2x', value: 2 },
    ];

    const shortcutList = [
      { key: 'Space', desc: 'Play / Pause' },
      { key: '\u2190', desc: 'Frame step backward' },
      { key: '\u2192', desc: 'Frame step forward' },
      { key: '+ / =', desc: 'Zoom in 0.5x' },
      { key: '-', desc: 'Zoom out 0.5x' },
      { key: '0', desc: 'Reset zoom' },
      { key: 'Home', desc: 'Seek to start' },
      { key: 'End', desc: 'Seek to end' },
    ];

    const savings = computed(() => props.sourceSize - props.encodedSize);
    const savingsPercent = computed(() => {
      if (props.sourceSize <= 0) return 0;
      return ((props.sourceSize - props.encodedSize) / props.sourceSize) * 100;
    });

    const vmafColor = computed(() => {
      if (props.vmafScore == null) return 'grey';
      if (props.vmafScore >= 90) return 'positive';
      if (props.vmafScore >= 70) return 'warning';
      return 'negative';
    });

    const frameCount = computed(() => Math.floor(duration.value * framerate.value));
    const currentFrame = computed(() => Math.floor(currentTime.value * framerate.value));

    // A3: Show mini-map when paused and zoomed > 2x
    const showMiniMap = computed(() => !playing.value && scale.value > 2);

    const containerStyle = computed(() => ({
      overflow: 'hidden',
      transform: `scale(${scale.value}) translate(${translateX.value}px, ${translateY.value}px)`,
      transformOrigin: 'center center',
      cursor: scale.value > 1 && !playing.value ? 'crosshair' : scale.value > 1 ? 'grab' : 'default',
    }));

    function onSourceLoaded() {
      if (sourceVideoRef.value) {
        duration.value = sourceVideoRef.value.duration || 0;
        const v = sourceVideoRef.value;
        if (v.videoWidth && v.videoHeight) {
          sourceResolution.value = `${v.videoWidth}\u00D7${v.videoHeight}`;
        }
      }
    }

    function onEncodedLoaded() {
      if (encodedVideoRef.value) {
        const v = encodedVideoRef.value;
        if (v.videoWidth && v.videoHeight) {
          encodedResolution.value = `${v.videoWidth}\u00D7${v.videoHeight}`;
        }
      }
    }

    function onVideoError(event) {
      const video = event.target;
      const src = video ? video.src : 'unknown';
      videoError.value = 'Failed to load video: ' + src;
      $q.notify({ type: 'negative', message: 'Video failed to load. The preview file may have been cleaned up.' });
    }

    function onSourceTimeUpdate() {
      if (!syncing.value && sourceVideoRef.value) {
        currentTime.value = sourceVideoRef.value.currentTime;
        // Handle looping
        if (looping.value && sourceVideoRef.value.ended) {
          seekToStart();
          if (playing.value) {
            sourceVideoRef.value.play();
            if (encodedVideoRef.value) encodedVideoRef.value.play();
          }
        }
      }
    }

    function syncVideos(time) {
      // Clamp to the shorter duration to avoid one video ending early
      const maxTime = encodedVideoRef.value
        ? Math.min(duration.value, encodedVideoRef.value.duration || duration.value)
        : duration.value;
      const clampedTime = Math.min(time, maxTime);
      syncing.value = true;
      if (sourceVideoRef.value) sourceVideoRef.value.currentTime = clampedTime;
      if (encodedVideoRef.value) encodedVideoRef.value.currentTime = clampedTime;
      // Use requestAnimationFrame to reset syncing after the browser processes the seek
      requestAnimationFrame(() => {
        syncing.value = false;
      });
    }

    function onSeek(val) { syncVideos(val); }

    function togglePlay() {
      if (playing.value) {
        if (sourceVideoRef.value) sourceVideoRef.value.pause();
        if (encodedVideoRef.value) encodedVideoRef.value.pause();
        playing.value = false;
      } else {
        if (sourceVideoRef.value) sourceVideoRef.value.play();
        if (encodedVideoRef.value) encodedVideoRef.value.play();
        playing.value = true;
      }
    }

    function frameNext() {
      const step = 1 / framerate.value;
      const newTime = Math.min(currentTime.value + step, duration.value);
      currentTime.value = newTime;
      syncVideos(newTime);
    }

    function framePrev() {
      const step = 1 / framerate.value;
      const newTime = Math.max(currentTime.value - step, 0);
      currentTime.value = newTime;
      syncVideos(newTime);
    }

    function seekToStart() {
      currentTime.value = 0;
      syncVideos(0);
    }

    function seekToEnd() {
      currentTime.value = duration.value;
      syncVideos(duration.value);
    }

    function onSpeedChange(speed) {
      if (sourceVideoRef.value) sourceVideoRef.value.playbackRate = speed;
      if (encodedVideoRef.value) encodedVideoRef.value.playbackRate = speed;
    }

    // A2: Zoom-to-Cursor
    function onZoom(event) {
      const delta = event.deltaY > 0 ? -0.2 : 0.2;
      const oldScale = scale.value;
      const newScale = Math.max(1, Math.min(8, oldScale + delta));
      if (newScale === oldScale) return;

      // Get cursor position relative to the container element
      const container = event.currentTarget;
      const rect = container.getBoundingClientRect();
      const cursorX = event.clientX - rect.left;
      const cursorY = event.clientY - rect.top;

      // Point under cursor in container coordinates (before transform)
      const containerCenterX = rect.width / 2;
      const containerCenterY = rect.height / 2;

      // The transform is: scale(s) translate(tx, ty) from center
      // Point in content space under cursor:
      const contentX = (cursorX - containerCenterX) / oldScale - translateX.value + containerCenterX;
      const contentY = (cursorY - containerCenterY) / oldScale - translateY.value + containerCenterY;

      // After new scale, we want the same content point under cursor:
      const newTranslateX = (cursorX - containerCenterX) / newScale - contentX + containerCenterX;
      const newTranslateY = (cursorY - containerCenterY) / newScale - contentY + containerCenterY;

      scale.value = newScale;

      if (newScale === 1) {
        translateX.value = 0;
        translateY.value = 0;
      } else {
        translateX.value = newTranslateX;
        translateY.value = newTranslateY;
      }
    }

    function resetZoom() {
      scale.value = 1;
      translateX.value = 0;
      translateY.value = 0;
    }

    // Pan
    function onPanStart(event) {
      if (scale.value <= 1) return;
      isPanning = true;
      panStartX = event.clientX;
      panStartY = event.clientY;
      panStartTranslateX = translateX.value;
      panStartTranslateY = translateY.value;
      document.addEventListener('mousemove', onPanMove);
      document.addEventListener('mouseup', onPanEnd);
    }

    function onPanMove(event) {
      if (!isPanning) return;
      translateX.value = panStartTranslateX + (event.clientX - panStartX) / scale.value;
      translateY.value = panStartTranslateY + (event.clientY - panStartY) / scale.value;
    }

    function onPanEnd() {
      isPanning = false;
      document.removeEventListener('mousemove', onPanMove);
      document.removeEventListener('mouseup', onPanEnd);
    }

    // Touch support for pan and zoom
    let lastTouchDistance = 0;

    function onTouchStart(event) {
      if (event.touches.length === 2) {
        // Pinch-to-zoom start
        const dx = event.touches[0].clientX - event.touches[1].clientX;
        const dy = event.touches[0].clientY - event.touches[1].clientY;
        lastTouchDistance = Math.sqrt(dx * dx + dy * dy);
      } else if (event.touches.length === 1 && scale.value > 1) {
        // Pan start
        isPanning = true;
        panStartX = event.touches[0].clientX;
        panStartY = event.touches[0].clientY;
        panStartTranslateX = translateX.value;
        panStartTranslateY = translateY.value;
      }
    }

    function onTouchMove(event) {
      if (event.touches.length === 2) {
        event.preventDefault();
        const dx = event.touches[0].clientX - event.touches[1].clientX;
        const dy = event.touches[0].clientY - event.touches[1].clientY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (lastTouchDistance > 0) {
          const scaleDelta = (dist - lastTouchDistance) * 0.01;
          scale.value = Math.max(1, Math.min(8, scale.value + scaleDelta));
          if (scale.value === 1) {
            translateX.value = 0;
            translateY.value = 0;
          }
        }
        lastTouchDistance = dist;
      } else if (event.touches.length === 1 && isPanning) {
        event.preventDefault();
        translateX.value = panStartTranslateX + (event.touches[0].clientX - panStartX) / scale.value;
        translateY.value = panStartTranslateY + (event.touches[0].clientY - panStartY) / scale.value;
      }
    }

    function onTouchEnd() {
      isPanning = false;
      lastTouchDistance = 0;
    }

    // Slider drag
    function onSliderDragStart(event) {
      isSliderDragging = true;
      document.addEventListener('mousemove', onSliderDragMove);
      document.addEventListener('mouseup', onSliderDragEnd);
    }

    function onSliderDragMove(event) {
      if (!isSliderDragging || !sliderViewportRef.value) return;
      const rect = sliderViewportRef.value.getBoundingClientRect();
      const x = event.clientX - rect.left;
      sliderPos.value = Math.max(0, Math.min(100, (x / rect.width) * 100));
    }

    function onSliderDragEnd() {
      isSliderDragging = false;
      document.removeEventListener('mousemove', onSliderDragMove);
      document.removeEventListener('mouseup', onSliderDragEnd);
    }

    // Slider touch drag
    function onSliderTouchStart(event) {
      isSliderDragging = true;
      document.addEventListener('touchmove', onSliderTouchMove, { passive: false });
      document.addEventListener('touchend', onSliderTouchEnd);
    }

    function onSliderTouchMove(event) {
      if (!isSliderDragging || !sliderViewportRef.value || !event.touches.length) return;
      event.preventDefault();
      const rect = sliderViewportRef.value.getBoundingClientRect();
      const x = event.touches[0].clientX - rect.left;
      sliderPos.value = Math.max(0, Math.min(100, (x / rect.width) * 100));
    }

    function onSliderTouchEnd() {
      isSliderDragging = false;
      document.removeEventListener('touchmove', onSliderTouchMove);
      document.removeEventListener('touchend', onSliderTouchEnd);
    }

    // Slider keyboard handler (Issue #18)
    function onSliderKeyDown(event) {
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        sliderPos.value = Math.max(0, sliderPos.value - 1);
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        sliderPos.value = Math.min(100, sliderPos.value + 1);
      }
    }

    // A1: Keyboard Shortcuts
    function onKeyDown(event) {
      // Guard against firing when input/select/textarea is focused
      const tag = event.target.tagName.toLowerCase();
      if (tag === 'input' || tag === 'select' || tag === 'textarea') return;

      // Skip arrow keys if a slider element is focused
      const activeRole = document.activeElement ? document.activeElement.getAttribute('role') : null;
      if (activeRole === 'slider' && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) return;

      switch (event.key) {
        case ' ':
          event.preventDefault();
          togglePlay();
          break;
        case 'ArrowLeft':
          event.preventDefault();
          framePrev();
          break;
        case 'ArrowRight':
          event.preventDefault();
          frameNext();
          break;
        case '+':
        case '=':
          event.preventDefault();
          scale.value = Math.min(8, scale.value + 0.5);
          break;
        case '-':
          event.preventDefault();
          scale.value = Math.max(1, scale.value - 0.5);
          if (scale.value === 1) {
            translateX.value = 0;
            translateY.value = 0;
          }
          break;
        case '0':
          event.preventDefault();
          resetZoom();
          break;
        case 'Home':
          event.preventDefault();
          seekToStart();
          break;
        case 'End':
          event.preventDefault();
          seekToEnd();
          break;
        default:
          break;
      }
    }

    // A3: Mini-Map rendering
    function drawMiniMap(canvasRef, videoRef) {
      const canvas = canvasRef.value;
      const video = videoRef.value;
      if (!canvas || !video) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      // Draw the video frame at low resolution
      ctx.drawImage(video, 0, 0, 120, 80);

      // Draw viewport rectangle
      // The visible portion is determined by scale and translate
      const viewportFractionW = 1 / scale.value;
      const viewportFractionH = 1 / scale.value;
      // Center offset from translate
      const offsetX = 0.5 - translateX.value / (video.videoWidth || 1) * scale.value;
      const offsetY = 0.5 - translateY.value / (video.videoHeight || 1) * scale.value;

      const rectW = 120 * viewportFractionW;
      const rectH = 80 * viewportFractionH;
      const rectX = (120 - rectW) / 2 - (translateX.value / (video.videoWidth || 120)) * 120;
      const rectY = (80 - rectH) / 2 - (translateY.value / (video.videoHeight || 80)) * 80;

      ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(
        Math.max(0, Math.min(120 - rectW, rectX)),
        Math.max(0, Math.min(80 - rectH, rectY)),
        rectW,
        rectH
      );
    }

    function updateMiniMaps() {
      if (!showMiniMap.value) return;
      nextTick(() => {
        drawMiniMap(sourceMiniMapRef, sourceVideoRef);
        drawMiniMap(encodedMiniMapRef, encodedVideoRef);
      });
    }

    // Watch for changes that should update mini-maps
    // Note: currentTime excluded since mini-map is only shown when paused (showMiniMap requires !playing)
    watch([showMiniMap, scale, translateX, translateY], () => {
      if (showMiniMap.value) {
        updateMiniMaps();
      }
    });

    // A5: Snapshot Feature
    function takeSnapshot() {
      if (playing.value) return;
      const srcVideo = sourceVideoRef.value;
      const encVideo = encodedVideoRef.value;
      if (!srcVideo || !encVideo) return;

      const srcW = srcVideo.videoWidth || 640;
      const srcH = srcVideo.videoHeight || 360;
      const encW = encVideo.videoWidth || 640;
      const encH = encVideo.videoHeight || 360;

      // Create a side-by-side canvas
      const maxH = Math.max(srcH, encH);
      const totalW = srcW + encW;
      const canvas = document.createElement('canvas');
      canvas.width = totalW;
      canvas.height = maxH;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, totalW, maxH);
      ctx.drawImage(srcVideo, 0, (maxH - srcH) / 2, srcW, srcH);
      ctx.drawImage(encVideo, srcW, (maxH - encH) / 2, encW, encH);

      // Add labels
      ctx.font = 'bold 16px sans-serif';
      ctx.fillStyle = 'rgba(0, 0, 128, 0.8)';
      ctx.fillRect(4, 4, 100, 24);
      ctx.fillStyle = '#fff';
      ctx.fillText('A - Original', 8, 22);

      ctx.fillStyle = 'rgba(0, 128, 0, 0.8)';
      ctx.fillRect(srcW + 4, 4, 100, 24);
      ctx.fillStyle = '#fff';
      ctx.fillText('B - Encoded', srcW + 8, 22);

      canvas.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const ts = new Date().toISOString().replace(/[:.]/g, '-');
        a.download = `preview_snapshot_${ts}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        $q.notify({ type: 'positive', message: 'Snapshot saved' });
      }, 'image/png');
    }

    // Lifecycle
    onMounted(() => {
      window.addEventListener('keydown', onKeyDown);
    });

    onBeforeUnmount(() => {
      // Pause videos to stop playback and free resources
      if (sourceVideoRef.value) sourceVideoRef.value.pause();
      if (encodedVideoRef.value) encodedVideoRef.value.pause();
      window.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('mousemove', onPanMove);
      document.removeEventListener('mouseup', onPanEnd);
      document.removeEventListener('mousemove', onSliderDragMove);
      document.removeEventListener('mouseup', onSliderDragEnd);
      document.removeEventListener('touchmove', onSliderTouchMove);
      document.removeEventListener('touchend', onSliderTouchEnd);
    });

    return {
      rootRef,
      sourceVideoRef,
      encodedVideoRef,
      sliderViewportRef,
      sourceMiniMapRef,
      encodedMiniMapRef,
      playing,
      currentTime,
      duration,
      viewMode,
      sliderPos,
      playbackSpeed,
      speedOptions,
      looping,
      scale,
      savings,
      savingsPercent,
      vmafColor,
      frameCount,
      currentFrame,
      showMiniMap,
      containerStyle,
      shortcutList,
      sourceResolution,
      encodedResolution,
      videoError,
      formatBytes,
      formatTime,
      onSourceLoaded,
      onEncodedLoaded,
      onSourceTimeUpdate,
      onVideoError,
      onSeek,
      togglePlay,
      frameNext,
      framePrev,
      seekToStart,
      seekToEnd,
      onSpeedChange,
      onZoom,
      resetZoom,
      onPanStart,
      onTouchStart,
      onTouchMove,
      onTouchEnd,
      onSliderDragStart,
      onSliderTouchStart,
      onSliderKeyDown,
      takeSnapshot,
    };
  }
}
</script>

<style scoped>
video {
  max-height: clamp(200px, 50vh, 500px);
  object-fit: contain;
  background: #000;
}

.video-container {
  position: relative;
}

.slider-viewport {
  position: relative;
  width: 100%;
  overflow: hidden;
}

.slider-video {
  width: 100%;
  max-height: 500px;
  object-fit: contain;
  background: #000;
  display: block;
}

.slider-source-clip {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.slider-source-clip video {
  max-height: 500px;
}

.slider-divider {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 4px;
  background: white;
  cursor: ew-resize;
  transform: translateX(-50%);
  z-index: 10;
}

.slider-handle {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 32px;
  height: 32px;
  background: white;
  border-radius: 50%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
}

.slider-handle::before {
  content: '\25C0\25B6';
  font-size: 10px;
  color: #333;
}

/* A/B Label Overlays */
.ab-label {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 5;
  padding: 4px 10px;
  border-radius: 4px;
  color: #fff;
  font-size: 12px;
  font-weight: bold;
  pointer-events: none;
  letter-spacing: 0.5px;
}

.ab-label-source {
  background: rgba(0, 0, 128, 0.7);
}

.ab-label-encoded {
  background: rgba(0, 128, 0, 0.7);
}

/* Slider A/B labels on divider */
.slider-ab-label {
  position: absolute;
  top: 8px;
  padding: 2px 6px;
  border-radius: 3px;
  color: #fff;
  font-size: 11px;
  font-weight: bold;
  pointer-events: none;
  white-space: nowrap;
}

.slider-ab-label-a {
  right: 8px;
  background: rgba(0, 0, 128, 0.7);
}

.slider-ab-label-b {
  left: 8px;
  background: rgba(0, 128, 0, 0.7);
}

/* Mini-Map */
.mini-map {
  position: absolute;
  bottom: 8px;
  right: 8px;
  width: 120px;
  height: 80px;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 4px;
  z-index: 15;
  pointer-events: none;
}

/* Video error overlay */
.video-error-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  color: #ff5252;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
  font-size: 14px;
  padding: 16px;
  text-align: center;
}

/* Focus outline for keyboard access */
.video-compare:focus {
  outline: 2px solid rgba(25, 118, 210, 0.5);
  outline-offset: 2px;
}
</style>
