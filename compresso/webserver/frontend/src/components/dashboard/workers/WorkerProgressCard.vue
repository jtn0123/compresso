<template>
  <q-card class="worker-progress-card nested-card">
    <q-card-section maxlength="2">
      <div class="row items-center no-wrap">
        <div class="col">
          <div class="text-h8 text-primary">
            {{ displayLabel }}
            <q-badge
              v-if="workerType"
              :color="workerType === 'gpu' ? 'green' : 'blue'"
              :label="workerType === 'gpu' ? $t('workers.gpuLabel') : $t('workers.cpuLabel')"
              class="q-ml-xs"
            />
            <q-tooltip v-if="label.length > 50" class="bg-white text-primary">{{ label }}</q-tooltip>
          </div>
        </div>

        <div class="col-auto">
          <q-btn
            @click="openDetails"
            color="secondary"
            dense
            round
            flat
            icon="open_in_full"
          >
            <q-tooltip class="bg-white text-primary">{{ $t('navigation.showMore') }}</q-tooltip>
          </q-btn>
        </div>
      </div>
    </q-card-section>

    <q-separator :style="'border-bottom:solid thin ' + workerGroupColour"/>

    <div class="row">
      <q-card-section class="q-pb-none col q-pb-none justify-center full-height full-width text-center">
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
      </q-card-section>

      <q-card-section class="q-pb-none col-7">
        <q-list bordered padding>
          <q-item>
            <q-item-section>
              <q-item-label>{{ $t('components.workers.stateLabel') }}</q-item-label>
              <q-item-label caption>
                {{ state }}
              </q-item-label>
            </q-item-section>
          </q-item>

          <q-item>
            <q-item-section>
              <q-item-label>{{ $t('components.workers.currentRunnerLabel') }}</q-item-label>
              <q-item-label caption>
                {{ currentRunner }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card-section>
    </div>

    <q-card-section v-if="!idle" class="q-pt-sm">
      <div class="row">
        <div class="column q-ml-sm">ETC:</div>
        <div class="column q-ml-lg">{{ etc }}</div>
        <q-tooltip class="bg-white text-primary">{{ $t('tooltips.etc') }}</q-tooltip>
      </div>
    </q-card-section>

    <!-- Mini CPU/RAM gauges -->
    <div v-if="!idle" class="q-px-md q-pb-sm">
      <div class="row items-center q-gutter-xs">
        <span class="text-caption text-grey">{{ $t('workers.cpuLabel') }}</span>
        <q-linear-progress :value="cpuValue" size="6px" class="col" color="secondary" :track-color="$q.dark.isActive ? 'grey-8' : 'grey-5'" />
        <span class="text-caption" :style="{color: cpuColor}">{{ cpuDisplay }}%</span>
      </div>
      <div class="row items-center q-gutter-xs q-mt-xs">
        <span class="text-caption text-grey">{{ $t('workers.memLabel') }}</span>
        <q-linear-progress :value="memValue" size="6px" class="col" color="secondary" :track-color="$q.dark.isActive ? 'grey-8' : 'grey-5'" />
        <span class="text-caption" :style="{color: memColor}">{{ memDisplay }}%</span>
      </div>
    </div>

    <WorkerMoreDetailsDialog
      ref="workerDetailsDialogRef"
      v-bind="props"
    />
  </q-card>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import { useWorkerGauges } from 'src/composables/useWorkerGauges'
import WorkerMoreDetailsDialog from 'components/dashboard/workers/WorkerMoreDetailsDialog.vue'

const $q = useQuasar()
const { t: $t } = useI18n()
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
    default: '#cccccc'
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
  },
  workerType: {
    type: String,
    default: ''
  }
})

const workerDetailsDialogRef = ref(null)

const cpuValue = computed(() => clampPercent(Number(props.subprocess?.cpu_percent || 0)) / 100)
const memValue = computed(() => clampPercent(Number(props.subprocess?.mem_percent || 0)) / 100)
const cpuDisplay = computed(() => formatPercent(clampPercent(Number(props.subprocess?.cpu_percent || 0))))
const memDisplay = computed(() => formatPercent(clampPercent(Number(props.subprocess?.mem_percent || 0))))
const cpuColor = computed(() => gradientColor(clampPercent(Number(props.subprocess?.cpu_percent || 0))))
const memColor = computed(() => gradientColor(clampPercent(Number(props.subprocess?.mem_percent || 0))))

const displayLabel = computed(() => {
  if (props.label.length < 50) {
    return props.label
  }
  return `${props.label.substring(0, 48)}..`
})

const openDetails = () => {
  workerDetailsDialogRef.value.show()
}
</script>

<style scoped>
.worker-progress-card {
  margin: 5px;
}
</style>
