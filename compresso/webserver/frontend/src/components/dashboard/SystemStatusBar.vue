<template>
  <div class="system-status-bar">
    <q-card-section class="q-pa-sm">
      <div class="row items-center q-col-gutter-sm">
        <!-- CPU -->
        <div class="col-6 col-sm-4 col-md">
          <div class="row items-center no-wrap q-gutter-xs">
            <span class="text-caption text-grey-7">{{ $t('systemStatus.cpu') }}</span>
            <q-linear-progress
              class="col"
              :value="liveMetrics.cpu_percent / 100"
              size="6px"
              rounded
              :color="cpuColor"
              :track-color="$q.dark.isActive ? 'grey-8' : 'grey-4'"
            />
            <span class="text-caption text-weight-medium" style="min-width: 36px; text-align: right">
              {{ Math.round(liveMetrics.cpu_percent) }}%
            </span>
          </div>
        </div>

        <!-- Memory -->
        <div class="col-6 col-sm-4 col-md">
          <div class="row items-center no-wrap q-gutter-xs">
            <span class="text-caption text-grey-7">{{ $t('systemStatus.memory') }}</span>
            <q-linear-progress
              class="col"
              :value="liveMetrics.memory_percent / 100"
              size="6px"
              rounded
              :color="memColor"
              :track-color="$q.dark.isActive ? 'grey-8' : 'grey-4'"
            />
            <span class="text-caption text-weight-medium" style="min-width: 36px; text-align: right">
              {{ Math.round(liveMetrics.memory_percent) }}%
            </span>
          </div>
        </div>

        <!-- Disk -->
        <div class="col-6 col-sm-4 col-md">
          <div class="row items-center no-wrap q-gutter-xs">
            <span class="text-caption text-grey-7">{{ $t('systemStatus.disk') }}</span>
            <q-linear-progress
              class="col"
              :value="liveMetrics.disk_percent / 100"
              size="6px"
              rounded
              :color="diskColor"
              :track-color="$q.dark.isActive ? 'grey-8' : 'grey-4'"
            />
            <span class="text-caption text-weight-medium" style="min-width: 36px; text-align: right">
              {{ Math.round(liveMetrics.disk_percent) }}%
            </span>
          </div>
        </div>

        <!-- GPU(s) -->
        <template v-if="liveGpus.length > 0">
          <div
            v-for="(gpu, i) in liveGpus"
            :key="'gpu-' + i"
            class="col-6 col-sm-4 col-md gt-xs"
          >
            <div class="row items-center no-wrap q-gutter-xs">
              <span class="text-caption text-grey-7">GPU{{ liveGpus.length > 1 ? gpu.index : '' }}</span>
              <q-linear-progress
                class="col"
                :value="gpu.utilization_percent / 100"
                size="6px"
                rounded
                :color="gpuColor(gpu.utilization_percent)"
                :track-color="$q.dark.isActive ? 'grey-8' : 'grey-4'"
              />
              <span class="text-caption text-weight-medium" style="min-width: 36px; text-align: right">
                {{ Math.round(gpu.utilization_percent) }}%
              </span>
              <q-tooltip>
                {{ gpu.memory_used_mb }}MB / {{ gpu.memory_total_mb }}MB &middot; {{ gpu.temperature_c }}&deg;C
              </q-tooltip>
            </div>
          </div>
        </template>
        <div v-else-if="gpuList.length > 0" class="col-6 col-sm-4 col-md gt-xs">
          <div class="row items-center no-wrap q-gutter-xs">
            <span class="text-caption text-grey-7">{{ $t('systemStatus.gpu') }}</span>
            <q-badge
              v-for="(gpu, i) in gpuList"
              :key="i"
              :color="gpu.type === 'nvidia' ? 'green-8' : 'blue-8'"
              :label="gpuDisplayName(gpu)"
              class="text-caption"
            />
          </div>
        </div>
        <div v-else class="col-6 col-sm-4 col-md gt-xs">
          <div class="row items-center no-wrap q-gutter-xs">
            <span class="text-caption text-grey-7">{{ $t('systemStatus.gpu') }}</span>
            <span class="text-caption text-grey">{{ $t('systemStatus.noGpu') }}</span>
          </div>
        </div>

        <!-- Connection Indicator -->
        <div class="col-auto">
          <div class="row items-center no-wrap q-gutter-xs">
            <q-icon
              name="circle"
              :color="connectionColor"
              size="8px"
              :class="{ 'pulse-animation': connectionState === 'connecting' }"
            />
            <q-tooltip>
              {{ connectionState === 'connected'
                ? $t('systemStatus.realtimeActive')
                : $t('systemStatus.realtimeLost') }}
            </q-tooltip>
            <span class="text-caption" :class="connectionTextClass">
              {{ connectionLabel }}
            </span>
          </div>
        </div>
      </div>
    </q-card-section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import { useWorkerGauges } from 'src/composables/useWorkerGauges'
import { wsConnectionState } from 'src/js/compressoWebsocket'

const $q = useQuasar()

const props = defineProps({
  systemInfo: { type: Object, default: null },
  liveMetrics: {
    type: Object,
    default: () => ({
      cpu_percent: 0,
      memory_percent: 0,
      memory_used_gb: 0,
      disk_percent: 0,
      disk_used_gb: 0,
      gpus: [],
    })
  }
})

const { t } = useI18n()
const { gradientColor } = useWorkerGauges()

const connectionState = computed(() => wsConnectionState.value)

const cpuColor = computed(() => gradientColor(props.liveMetrics.cpu_percent))
const memColor = computed(() => gradientColor(props.liveMetrics.memory_percent))
const diskColor = computed(() => gradientColor(props.liveMetrics.disk_percent))

const liveGpus = computed(() => props.liveMetrics.gpus || [])

const gpuList = computed(() => {
  return props.systemInfo?.gpus || []
})

const gpuColor = (percent) => gradientColor(percent)

function gpuDisplayName(gpu) {
  if (gpu.type === 'nvidia') return gpu.name || 'NVIDIA'
  if (gpu.type === 'vaapi') return 'VAAPI'
  return gpu.name || gpu.type
}

const connectionColor = computed(() => {
  switch (connectionState.value) {
    case 'connected': return 'positive'
    case 'connecting': return 'warning'
    default: return 'negative'
  }
})

const connectionTextClass = computed(() => {
  switch (connectionState.value) {
    case 'connected': return 'text-positive'
    case 'connecting': return 'text-warning'
    default: return 'text-negative'
  }
})

const connectionLabel = computed(() => {
  switch (connectionState.value) {
    case 'connected': return t('systemStatus.connected')
    case 'connecting': return t('systemStatus.connecting')
    default: return t('systemStatus.disconnected')
  }
})
</script>

<style scoped>
.system-status-bar {
  background: rgba(26, 107, 74, 0.04);
  border-radius: 6px;
  border: 1px solid rgba(26, 107, 74, 0.1);
}

.body--dark .system-status-bar {
  background: rgba(34, 145, 106, 0.08);
  border-color: rgba(34, 145, 106, 0.15);
}

.pulse-animation {
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
