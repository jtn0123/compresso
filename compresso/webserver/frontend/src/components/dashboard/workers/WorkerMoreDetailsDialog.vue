<template>
  <CompressoDialogWindow
    ref="dialogRef"
    :title="label"
    @hide="onDialogHide"
  >
    <div
      class="worker-details-body column full-height"
      :class="{ 'scroll-enabled': isMobile || $q.screen.lt.md }"
      :style="{ '--worker-border': workerGroupColour }"
    >
      <div class="row worker-top-row">
        <!--START GAUGES-->
        <q-card-section class="col-12 worker-progress-section">
          <div class="worker-gauges-shell">
            <q-circular-progress
              :indeterminate="indeterminate"
              show-value
              :value="progress"
              size="90px"
              :thickness="0.2"
              :color="color"
              :center-color="$q.dark.isActive ? 'grey-10' : 'grey-1'"
              :track-color="$q.dark.isActive ? 'grey-8' : 'grey-4'"
              font-size="10px"
              class="q-ma-md"
            >
              <q-avatar size="60px">
                {{ progressText }}
              </q-avatar>
            </q-circular-progress>

            <q-separator class="worker-gauges-separator"/>

            <div class="worker-gauges">
              <div class="text-caption text-grey-7 q-mt-sm">
                {{ $t('components.workers.cpuUsage') }}:
                <span :style="{ color: cpuTextColor }">{{ cpuPercentDisplay }}%</span>
              </div>
              <q-linear-progress
                :value="cpuPercentValue"
                class="q-mb-sm"
                color="secondary"
                :track-color="$q.dark.isActive ? 'grey-8' : 'grey-5'"
                size="20px"
              />

              <div class="text-caption text-grey-7">
                {{ $t('components.workers.memoryUsage') }}:
                <span :style="{ color: memTextColor }">{{ memPercentDisplay }}%</span>
              </div>
              <q-linear-progress
                :value="memPercentValue"
                color="secondary"
                :track-color="$q.dark.isActive ? 'grey-8' : 'grey-5'"
                size="20px"
              />
            </div>
          </div>
        </q-card-section>
        <!--END GAUGES-->

        <!--START STATUS-->
        <q-card-section class="col-12 worker-status-section">
          <WorkerProgressStatusCard
            :id="id"
            :state="state"
            :currentRunner="currentRunner"
            :startTime="startTime"
            :timeSinceStart="timeSinceStart"
            :elapsed="elapsed"
            :etc="etc"
            :currentCommand="currentCommand"
            :paused="paused"
            :idle="idle"
          />
        </q-card-section>
        <!--END STATUS-->
      </div>

      <div class="row worker-log-row">
        <!--START WORKER LOG-->
        <q-card-section class="col worker-log-section">
          <WorkerProgressLogCard :workerLog="workerLog"/>
        </q-card-section>
        <!--END WORKER LOG-->
      </div>
    </div>
  </CompressoDialogWindow>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useQuasar } from 'quasar'
import { useMobile } from 'src/composables/useMobile'
import { useWorkerGauges } from 'src/composables/useWorkerGauges'
import CompressoDialogWindow from 'components/ui/dialogs/CompressoDialogWindow.vue'
import WorkerProgressStatusCard from 'components/dashboard/workers/partials/WorkerProgressStatusCard.vue'
import WorkerProgressLogCard from 'components/dashboard/workers/partials/WorkerProgressLogCard.vue'

const $q = useQuasar()
const { isMobile } = useMobile()
const { clampPercent, formatPercent, gradientColor } = useWorkerGauges()

const props = defineProps({
  id: {
    type: String,
    required: true
  },
  label: {
    type: String,
    required: true
  },
  name: {
    type: String,
    required: true
  },
  progress: {
    type: Number,
    default: 100
  },
  progressText: {
    type: String,
    default: ''
  },
  elapsed: {
    type: String,
    default: ''
  },
  etc: {
    type: String,
    default: ''
  },
  color: {
    type: String,
    default: 'warning'
  },
  workerGroupColour: {
    type: String,
    default: 'var(--compresso-grey-4)'
  },
  state: {
    type: String,
    default: 'Waiting for another task...'
  },
  currentRunner: {
    type: String,
    default: ''
  },
  startTime: {
    type: String,
    default: ''
  },
  timeSinceStart: {
    type: String,
    default: ''
  },
  indeterminate: {
    type: Boolean,
    default: false
  },
  currentCommand: {
    type: String,
    default: ''
  },
  currentFile: {
    type: String,
    default: ''
  },
  currentTask: {
    type: Number,
    default: null
  },
  runnersInfo: {
    type: Object,
    default: () => ({})
  },
  subprocess: {
    type: Object,
    default: () => ({})
  },
  workerLog: {
    type: Array,
    default: () => []
  },
  idle: {
    type: Boolean,
    default: false
  },
  paused: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['hide'])

const dialogRef = ref(null)

const cpuPercentValue = computed(() => {
  const value = clampPercent(Number(props.subprocess?.cpu_percent || 0))
  return value / 100
})
const memPercentValue = computed(() => {
  const value = clampPercent(Number(props.subprocess?.mem_percent || 0))
  return value / 100
})
const cpuPercentDisplay = computed(() => {
  const value = clampPercent(Number(props.subprocess?.cpu_percent || 0))
  return formatPercent(value)
})
const memPercentDisplay = computed(() => {
  const value = clampPercent(Number(props.subprocess?.mem_percent || 0))
  return formatPercent(value)
})
const cpuTextColor = computed(() => {
  const value = clampPercent(Number(props.subprocess?.cpu_percent || 0))
  return gradientColor(value)
})
const memTextColor = computed(() => {
  const value = clampPercent(Number(props.subprocess?.mem_percent || 0))
  return gradientColor(value)
})

const show = () => {
  dialogRef.value.show()
}

const hide = () => {
  dialogRef.value.hide()
}

const onDialogHide = () => {
  emit('hide')
}

defineExpose({
  show,
  hide
})
</script>

<style scoped>
.worker-details-body {
  border-top: solid thin var(--worker-border);
  height: 100%;
  overflow: hidden;
  flex: 1;
  min-height: 0;
}

.worker-details-body.scroll-enabled {
  overflow: visible;
  height: auto;
  display: block;
}

.worker-top-row {
  flex: 0 0 auto;
  flex-wrap: nowrap;
}

.worker-progress-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1 1 0;
}

.worker-status-section {
  flex: 0 0 700px;
  max-width: 700px;
  margin-left: auto;
}

.worker-gauges-shell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
}

.worker-gauges {
  width: 95%;
  max-width: 450px;
  text-align: left;
}

.worker-gauges-separator {
  width: 100%;
  max-width: 180px;
  margin: 4px 0 8px;
}

@media (max-width: 1023px) {
  .worker-top-row {
    flex-wrap: wrap;
  }

  .worker-progress-section {
    flex: 1 1 100%;
  }

  .worker-status-section {
    flex: 1 1 100%;
    max-width: none;
    margin-left: 0;
  }
}

.worker-log-row {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.worker-details-body.scroll-enabled .worker-log-row {
  flex: none;
  overflow: visible;
  height: auto;
}

.worker-log-section {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

:deep(.worker-log-card) {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

:deep(.worker-log-card .q-card-section:last-child) {
  flex: 1;
  overflow: auto;
  min-height: 0;
}
</style>
