<template>
  <q-card flat bordered class="full-height">
    <q-card-section class="bg-card-head">
      <div class="row items-center no-wrap">
        <div class="col">
          <div class="text-h6 text-primary">
            <q-icon name="fas fa-spinner" />
            {{ $t('headers.workers') }}
          </div>
        </div>
        <div class="col-auto">
          <q-btn-dropdown
            class="q-ml-sm"
            outline
            content-class="compresso-dropdown-menu"
            :color="hasWorkers ? 'secondary' : 'grey-7'"
            :disable-main-btn="!hasWorkers"
            :label="$t('navigation.options')"
          >
            <q-list>
              <q-item clickable @click="$emit('pause-all')" v-close-popup>
                <q-item-section>
                  <q-item-label>
                    <q-icon name="pause" />
                    {{ $t('components.workers.pauseAllWorkers') }}
                  </q-item-label>
                </q-item-section>
              </q-item>
              <q-item clickable @click="$emit('resume-all')" v-close-popup>
                <q-item-section>
                  <q-item-label>
                    <q-icon name="play_arrow" />
                    {{ $t('components.workers.resumeAllWorkers') }}
                  </q-item-label>
                </q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable @click="$emit('terminate-all')" v-close-popup>
                <q-item-section>
                  <q-item-label>
                    <q-icon name="fas fa-skull-crossbones" />
                    {{ $t('components.workers.terminateAllWorkers') }}
                  </q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-btn-dropdown>
        </div>
      </div>
    </q-card-section>

    <q-card-section class="q-pa-sm">
      <div v-if="!hasWorkers" class="full-width row flex-center text-accent q-gutter-sm q-pa-md">
        <q-item-label>{{ $t('components.workers.listEmpty') }}</q-item-label>
      </div>

      <div v-for="group in workerGroups" :key="group.name" class="q-mb-md">
        <!-- Group Header -->
        <div
          class="row items-center no-wrap q-pa-xs q-mb-xs"
          :style="{ borderLeft: '3px solid ' + group.color }"
        >
          <q-badge
            :color="group.workerType === 'gpu' ? 'green' : 'blue'"
            :label="group.workerType === 'gpu' ? $t('workers.gpuLabel') : $t('workers.cpuLabel')"
            class="q-mr-xs"
          />
          <span class="text-subtitle2 text-weight-medium q-mr-sm">{{ group.name }}</span>
          <span class="text-caption text-grey q-mr-xs">
            <span v-if="group.active > 0" class="text-positive">{{ group.active }} {{ $t('workers.activeCount', { count: group.active }) }}</span>
            <span v-if="group.idle > 0" class="q-ml-xs text-grey">{{ $t('workers.idleCount', { count: group.idle }) }}</span>
            <span v-if="group.paused > 0" class="q-ml-xs text-negative">{{ $t('workers.pausedCount', { count: group.paused }) }}</span>
          </span>
          <q-space />
          <q-btn
            dense flat round size="xs" icon="remove"
            :disable="(group.workerCount || 0) <= 0 || group.saving"
            @click.stop="changeGroupWorkerCount(group, -1)"
          />
          <span class="text-caption text-weight-medium q-mx-xs">{{ group.workerCount ?? '?' }}</span>
          <q-btn
            dense flat round size="xs" icon="add"
            :disable="group.saving"
            @click.stop="changeGroupWorkerCount(group, 1)"
          />
        </div>

        <!-- Worker Rows -->
        <div
          v-for="worker in group.workers"
          :key="worker.id"
          class="row items-center no-wrap q-px-sm q-py-xs worker-row"
        >
          <!-- Worker name -->
          <div class="col-3 text-caption text-truncate">
            {{ workerShortName(worker.name) }}
          </div>

          <!-- Progress bar -->
          <div class="col q-px-xs">
            <template v-if="!worker.idle && !worker.paused">
              <q-linear-progress
                :value="worker.progress / 100"
                :indeterminate="worker.indeterminate"
                :class="{ 'worker-progress-active': !worker.indeterminate }"
                size="20px"
                rounded
                color="secondary"
                track-color="transparent"
              >
                <div class="absolute-full flex flex-center">
                  <span class="text-caption text-white" style="text-shadow: 0 0 3px rgba(0,0,0,0.5)">
                    {{ truncateFile(worker.currentFile) }}
                    <template v-if="!worker.indeterminate">{{ worker.progressText }}</template>
                  </span>
                </div>
              </q-linear-progress>
            </template>
            <template v-else-if="worker.paused">
              <span class="text-caption text-negative">{{ $t('components.workers.state.paused') }}</span>
            </template>
            <template v-else>
              <span class="text-caption text-grey">{{ $t('components.workers.state.waiting') }}</span>
            </template>
          </div>

          <!-- Encoding stats -->
          <div v-if="!worker.idle && !worker.paused && (worker.encodingFps != null || worker.encodingSpeed)" class="col-auto text-caption q-px-xs worker-encoding-stats">
            <span v-if="worker.encodingFps != null" class="worker-fps">{{ worker.encodingFps }} {{ $t('workerStats.fps') }}</span>
            <span v-if="worker.encodingSpeed" class="worker-speed q-ml-xs">{{ worker.encodingSpeed }}</span>
          </div>

          <!-- ETC -->
          <div class="col-auto text-caption text-grey q-px-xs" style="min-width: 55px; text-align: right">
            {{ (!worker.idle && !worker.paused) ? worker.etc : '' }}
          </div>

          <!-- Expand -->
          <div class="col-auto">
            <q-btn
              dense round flat size="xs" icon="open_in_full"
              color="secondary"
              @click="openWorkerDetails(worker)"
            >
              <q-tooltip>{{ $t('navigation.showMore') }}</q-tooltip>
            </q-btn>
          </div>
        </div>
      </div>
    </q-card-section>

    <WorkerMoreDetailsDialog
      ref="workerDetailsDialogRef"
      v-bind="selectedWorkerProps"
    />
  </q-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { useWorkerGauges } from 'src/composables/useWorkerGauges'
import WorkerMoreDetailsDialog from 'components/dashboard/workers/WorkerMoreDetailsDialog.vue'

const $q = useQuasar()
const { t: $t } = useI18n()
const { generateGroupColour } = useWorkerGauges()

const props = defineProps({
  workerProgressList: {
    type: Object,
    default: () => ({})
  }
})

defineEmits(['pause-all', 'resume-all', 'terminate-all'])

const workerGroupConfigs = ref({})
const savingGroups = ref({})
const workerDetailsDialogRef = ref(null)
const selectedWorkerProps = ref({
  id: '',
  label: '',
  name: '',
  progress: 100,
  progressText: '',
  elapsed: '',
  etc: '',
  color: 'warning',
  workerGroupColour: 'var(--compresso-grey-4)',
  state: '',
  currentRunner: '',
  startTime: '',
  timeSinceStart: '',
  indeterminate: false,
  currentCommand: '',
  currentFile: '',
  currentTask: null,
  runnersInfo: {},
  subprocess: {},
  workerLog: [],
  idle: false,
  paused: false
})

const hasWorkers = computed(() => Object.keys(props.workerProgressList).length > 0)

const workerGroups = computed(() => {
  const groups = {}
  for (const key in props.workerProgressList) {
    const worker = props.workerProgressList[key]
    const nameParts = worker.name ? worker.name.split('-Worker-') : []
    const groupName = nameParts.length > 0 ? nameParts[0] : 'Unknown'

    if (!groups[groupName]) {
      const config = workerGroupConfigs.value[groupName] || {}
      groups[groupName] = {
        name: groupName,
        active: 0,
        idle: 0,
        paused: 0,
        color: worker.workerGroupColour || generateGroupColour(groupName),
        workerType: config.worker_type || worker.workerType || 'cpu',
        workerCount: config.number_of_workers ?? null,
        groupId: config.id ?? null,
        saving: savingGroups.value[groupName] || false,
        workers: []
      }
    }

    if (worker.paused) {
      groups[groupName].paused++
    } else if (worker.idle) {
      groups[groupName].idle++
    } else {
      groups[groupName].active++
    }

    groups[groupName].workers.push(worker)
  }
  return Object.values(groups)
})

function workerShortName(name) {
  if (!name) return ''
  const parts = name.split('-Worker-')
  return parts.length > 1 ? 'W-' + parts[1] : name
}

function truncateFile(file) {
  if (!file) return ''
  const name = file.split('/').pop()
  if (name.length > 25) return name.substring(0, 23) + '..'
  return name
}

function openWorkerDetails(worker) {
  selectedWorkerProps.value = {
    id: worker.id || '',
    label: worker.label || '',
    name: worker.name || '',
    progress: worker.progress ?? 100,
    progressText: worker.progressText || '',
    elapsed: worker.elapsed || '',
    etc: worker.etc || '',
    color: worker.color || 'warning',
    workerGroupColour: worker.workerGroupColour || 'var(--compresso-grey-4)',
    state: worker.state || '',
    currentRunner: worker.currentRunner || '',
    startTime: worker.startTime || '',
    timeSinceStart: worker.timeSinceStart || '',
    indeterminate: worker.indeterminate || false,
    currentCommand: worker.currentCommand || '',
    currentFile: worker.currentFile || '',
    currentTask: worker.currentTask ?? null,
    runnersInfo: worker.runnersInfo || {},
    subprocess: worker.subprocess || {},
    workerLog: worker.workerLog || [],
    idle: worker.idle || false,
    paused: worker.paused || false
  }
  workerDetailsDialogRef.value.show()
}

async function fetchWorkerGroupConfigs() {
  try {
    const response = await axios.get(getCompressoApiUrl('v2', 'settings/worker_groups'))
    const configs = {}
    for (const group of response.data.worker_groups) {
      configs[group.name] = {
        id: group.id,
        worker_type: group.worker_type || 'cpu',
        number_of_workers: group.number_of_workers || 0
      }
    }
    workerGroupConfigs.value = configs
  } catch (_e) {
    // Will default to 'cpu' and no count
  }
}

async function changeGroupWorkerCount(group, delta) {
  if (group.groupId === null) return
  const newCount = Math.max(0, (group.workerCount || 0) + delta)
  savingGroups.value[group.name] = true
  try {
    await axios.post(getCompressoApiUrl('v2', 'settings/worker_group/write'), {
      id: group.groupId,
      number_of_workers: newCount
    })
    if (workerGroupConfigs.value[group.name]) {
      workerGroupConfigs.value[group.name].number_of_workers = newCount
    }
    $q.notify({
      color: 'positive',
      position: 'top',
      message: $t('workers.workerCountUpdated'),
      icon: 'check_circle',
      actions: [{ icon: 'close', color: 'white' }]
    })
  } catch (_e) {
    $q.notify({
      color: 'negative',
      position: 'top',
      message: $t('workers.workerCountFailed'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }]
    })
  } finally {
    savingGroups.value[group.name] = false
  }
}

onMounted(() => {
  fetchWorkerGroupConfigs()
})
</script>

<style scoped>
.worker-row {
  border-radius: 4px;
  transition: background-color 0.15s;
}
.worker-row:hover {
  background-color: color-mix(in srgb, var(--q-primary), transparent 95%);
}
.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.worker-encoding-stats {
  min-width: 80px;
  text-align: right;
}
.worker-fps {
  color: var(--q-info);
}
.worker-speed {
  color: var(--compresso-grey-6);
}
</style>
