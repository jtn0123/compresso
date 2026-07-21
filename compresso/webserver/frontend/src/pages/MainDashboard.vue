<template>
  <q-page padding class="q-pa-sm" data-testid="dashboard-page">
    <div class="row q-col-gutter-md">
      <!-- Row 1: Hero section -->
      <!-- Left: Donut + Stats -->
      <div class="col-12 col-md-4 col-lg-3">
        <q-card flat bordered class="full-height">
          <q-card-section class="q-pa-sm">
            <LibraryDonutChart
              :total-files="optimizationData.totalFiles"
              :processed-files="optimizationData.processedFiles"
              :percent="optimizationData.percent"
              :loading="optimizationData.loading"
            />
          </q-card-section>
          <q-separator />
          <q-card-section class="q-pa-sm">
            <CompactStatsGrid />
          </q-card-section>
        </q-card>
      </div>

      <!-- Right: Workers -->
      <div class="col-12 col-md-8 col-lg-9">
        <WorkersPanel
          :worker-progress-list="workerProgressList"
          @pause-all="pauseAllWorkers"
          @resume-all="resumeAllWorkers"
          @terminate-all="terminateAllWorkers"
        />

        <!-- Stale data warning -->
        <div v-if="workersStale" class="q-mt-sm">
          <q-banner dense class="bg-warning text-dark text-caption" rounded>
            <template #avatar>
              <q-icon name="warning" color="dark" />
            </template>
            {{ $t('common.dataStale') }}
          </q-banner>
        </div>
      </div>

      <!-- Row 2.5: GPU Utilization -->
      <div v-if="liveMetrics.gpus && liveMetrics.gpus.length > 0" class="col-12">
        <q-card flat bordered>
          <q-card-section class="bg-card-head q-pa-sm">
            <div class="text-heading text-primary">
              <q-icon name="memory" size="18px" class="q-mr-xs" />
              {{ $t('gpu.cardTitle') }}
            </div>
          </q-card-section>
          <q-card-section class="q-pa-sm">
            <div
              v-for="(gpu, i) in liveMetrics.gpus"
              :key="'gpu-stat-' + i"
              class="row items-center no-wrap q-py-xs q-col-gutter-sm"
            >
              <div class="col-auto text-caption text-weight-medium" style="min-width: 140px">
                {{ gpu.name || 'GPU ' + gpu.index }}
              </div>
              <div class="col-auto">
                <q-badge
                  :color="
                    (gpu.utilization_percent ?? 0) > 80
                      ? 'negative'
                      : (gpu.utilization_percent ?? 0) > 50
                        ? 'warning'
                        : 'positive'
                  "
                  :label="Math.round(gpu.utilization_percent ?? 0) + '%'"
                />
              </div>
              <div class="col q-px-sm">
                <q-linear-progress
                  :value="(gpu.memory_used_mb || 0) / (gpu.memory_total_mb || 1)"
                  size="6px"
                  color="info"
                  track-color="transparent"
                >
                  <q-tooltip>
                    {{ $t('gpu.memory') }}: {{ gpu.memory_used_mb }}MB / {{ gpu.memory_total_mb }}MB
                  </q-tooltip>
                </q-linear-progress>
              </div>
              <div class="col-auto text-caption text-grey" style="min-width: 50px; text-align: right">
                <template v-if="gpu.temperature_c != null"> {{ gpu.temperature_c }}&deg;C </template>
              </div>
            </div>
          </q-card-section>
          <q-card-section class="q-pt-none">
            <GpuUtilizationChart :gpu-history="gpuHistory" />
          </q-card-section>
        </q-card>
      </div>

      <!-- Row 3: Tasks -->
      <div class="col-12 col-md-5">
        <PendingTasks v-bind="pendingTasksData" :queue-eta="queueEta" />
      </div>
      <div class="col-12 col-md-7">
        <CompletedTasks v-bind="completedTasksData" />
      </div>

      <!-- Row 4: Bottom panels -->
      <div class="col-12 col-md-6">
        <LinkedNodesPanel />
      </div>
      <div class="col-12 col-md-6">
        <HealthCheckPanel />
      </div>
    </div>

    <ReleaseNotesDialog />
  </q-page>
</template>

<script lang="ts">
import LibraryDonutChart from 'components/charts/LibraryDonutChart.vue'
import CompactStatsGrid from 'components/dashboard/CompactStatsGrid.vue'
import WorkersPanel from 'components/dashboard/workers/WorkersPanel.vue'
import LinkedNodesPanel from 'components/dashboard/LinkedNodesPanel.vue'
import HealthCheckPanel from 'components/dashboard/HealthCheckPanel.vue'
import PendingTasks from 'components/dashboard/pending/PendingTasksDashboardSection.vue'
import CompletedTasks from 'components/dashboard/completed/CompletedTasksDashboardSection.vue'
import dateTools from 'src/js/dateTools'
import { defineComponent, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CompressoWebsocketHandler } from 'src/js/compressoWebsocket'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import type { CompressoSocket } from 'src/js/compressoGlobals'
import ReleaseNotesDialog from 'components/docs/ReleaseNotesDialog.vue'
import GpuUtilizationChart from 'components/charts/GpuUtilizationChart.vue'
import { useWorkerGauges } from 'src/composables/useWorkerGauges'
import { useSystemStatus } from 'src/composables/useSystemStatus'
import { createLogger } from 'src/composables/useLogger'
import type { ApiSchema } from 'src/types/contracts'
import {
  parseDashboardEnvelope,
  type CompletedTaskSummary,
  type CompletedTasksMessage,
  type PendingTaskSummary,
  type PendingTasksMessage,
  type QueueEta,
} from 'src/types/dashboard'
import type { WorkerInfoMessage, WorkerProgressEntry } from 'src/types/workers'

export default defineComponent({
  name: 'MainDashboard',
  components: {
    ReleaseNotesDialog,
    CompletedTasks,
    LibraryDonutChart,
    CompactStatsGrid,
    WorkersPanel,
    LinkedNodesPanel,
    HealthCheckPanel,
    PendingTasks,
    GpuUtilizationChart,
  },
  setup() {
    const { t: $t } = useI18n()
    const log = createLogger('Dashboard')
    const { generateGroupColour } = useWorkerGauges()
    const {
      systemInfo,
      liveMetrics,
      gpuHistory,
      fetchSystemInfo,
      startLiveMetrics,
      stopLiveMetrics,
      updateLiveMetrics,
    } = useSystemStatus()
    const lastWorkersUpdate = ref<number | null>(null)
    const workersStale = ref(false)
    const workerProgressList = ref<Record<string, WorkerProgressEntry>>({})
    const pendingTasksData = ref<{ taskList: PendingTaskSummary[] }>({
      taskList: [],
    })
    const completedTasksData = ref<{ taskList: CompletedTaskSummary[] }>({
      taskList: [],
    })
    const optimizationData = ref({
      totalFiles: 0,
      processedFiles: 0,
      percent: 0,
      loading: true,
    })
    const queueEta = ref<QueueEta | null>(null)

    function formatDuration(seconds: number | null | undefined): string | null {
      if (seconds == null || seconds <= 0) return null
      if (seconds < 60) return '< 1m'
      const hours = Math.floor(seconds / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)
      if (hours > 0) return hours + 'h ' + minutes + 'm'
      return minutes + 'm'
    }

    let ws: CompressoSocket | null = null
    const compressoWSHandler = CompressoWebsocketHandler($t)
    let queuedWorkersPayload: WorkerInfoMessage[] | null = null
    let queuedWorkerUpdate = false

    const workerGroupColours: Record<string, string> = {}

    function getWorkerGroupColour(workerName: string): string {
      const current = workerGroupColours[workerName]
      if (current) return current
      const generated = generateGroupColour(workerName)
      workerGroupColours[workerName] = generated
      return generated
    }

    function buildWorkerProgressEntry(worker: WorkerInfoMessage): WorkerProgressEntry {
      function calculateEtc(percentCompleted: number, timeElapsed: number): number {
        const percentToGo = 100 - percentCompleted
        return (timeElapsed / percentCompleted) * percentToGo
      }

      const workerGroupColour = getWorkerGroupColour(worker.name)
      const workerEntry: WorkerProgressEntry = {
        indeterminate: false,
        id: String(worker.id),
        label: worker.name,
        name: worker.name,
        color: 'warning',
        progress: 100,
        progressText: '-',
        elapsed: '',
        etc: '...',
        state: $t('components.workers.state.waiting'),
        currentRunner: $t('components.workers.currentRunner.none'),
        startTime: '',
        timeSinceStart: '',
        currentCommand: '',
        workerLog: [],
        idle: worker.idle,
        paused: worker.paused,
        workerGroupColour,
        workerType: worker.worker_type || worker.workerType || '',
        currentFile: worker.current_file || '',
        currentTask: worker.current_task ?? null,
        runnersInfo: worker.runners_info || {},
        subprocess: worker.subprocess || {},
        encodingFps: null,
        encodingSpeed: null,
      }

      if (worker.paused) {
        workerEntry.color = 'negative'
        workerEntry.progressText = '...'
        workerEntry.state = $t('components.workers.state.paused')
      }

      if (!worker.idle) {
        workerEntry.label = worker.current_file ? `${worker.name}: ${worker.current_file}` : worker.name
        workerEntry.color = 'secondary'
        workerEntry.state = $t('components.workers.state.processing')

        let currentRunner = $t('components.workers.currentRunner.indeterminate')
        if (typeof worker.runners_info === 'object' && worker.runners_info !== null) {
          for (const runnerValue of Object.values(worker.runners_info)) {
            if (runnerValue.status === 'in_progress') {
              currentRunner = runnerValue.name ?? currentRunner
            }
          }
        }
        workerEntry.currentRunner = currentRunner

        const processingDuration = worker.start_time ? (Date.now() - worker.start_time * 1000) / 1000 : 0
        workerEntry.startTime = worker.start_time ? dateTools.printDateTimeString(worker.start_time) : ''
        workerEntry.timeSinceStart = processingDuration > 0 ? dateTools.printSecondsAsDuration(processingDuration) : ''
        workerEntry.currentCommand = worker.current_command || ''
        workerEntry.workerLog = worker.worker_log_tail || []

        const percentValue = Number(worker.subprocess?.percent)
        const elapsedValue = Number(worker.subprocess?.elapsed)
        const hasPercent = Number.isFinite(percentValue) && worker.subprocess?.percent !== ''
        const hasElapsed = Number.isFinite(elapsedValue) && elapsedValue >= 0
        const canEstimate = hasPercent && percentValue > 0 && hasElapsed

        if (hasPercent) {
          workerEntry.progress = percentValue
          workerEntry.progressText = `${worker.subprocess.percent}%`
        } else {
          workerEntry.indeterminate = true
          workerEntry.progressText = '...'
        }

        if (canEstimate) {
          workerEntry.elapsed = dateTools.printSecondsAsDuration(elapsedValue)
          // Prefer backend ETA when available, fall back to frontend calculation
          const backendEta = Number(worker.subprocess?.eta_seconds)
          if (Number.isFinite(backendEta) && backendEta > 0) {
            workerEntry.etc = formatDuration(backendEta) ?? '...'
          } else {
            workerEntry.etc = dateTools.printSecondsAsDuration(calculateEtc(percentValue, elapsedValue))
          }
        }

        // Encoding FPS and speed from backend
        const encodingFps = Number(worker.subprocess?.encoding_fps)
        const encodingSpeed = Number(worker.subprocess?.encoding_speed)
        workerEntry.encodingFps = Number.isFinite(encodingFps) && encodingFps > 0 ? encodingFps.toFixed(1) : null
        workerEntry.encodingSpeed =
          Number.isFinite(encodingSpeed) && encodingSpeed > 0 ? encodingSpeed.toFixed(1) + 'x' : null

        if (worker.paused) {
          workerEntry.indeterminate = true
          workerEntry.color = 'negative'
          workerEntry.state = $t('components.workers.state.paused')
        }
      }

      return workerEntry
    }

    function updateWorkerProgressCharts(data: WorkerInfoMessage[]): void {
      const nextWorkerKeys = new Set<string>()
      for (let i = 0; i < data.length; i++) {
        const worker = data[i]
        if (!worker) continue
        const workerKey = 'worker-' + worker.id
        nextWorkerKeys.add(workerKey)

        const nextWorkerState = buildWorkerProgressEntry(worker)
        const existingWorker = workerProgressList.value[workerKey]
        if (existingWorker) {
          Object.assign(existingWorker, nextWorkerState)
        } else {
          workerProgressList.value[workerKey] = nextWorkerState
        }
      }

      Object.keys(workerProgressList.value).forEach((workerKey) => {
        if (!nextWorkerKeys.has(workerKey)) {
          delete workerProgressList.value[workerKey]
        }
      })
    }

    function queueWorkerProgressUpdate(data: WorkerInfoMessage[]): void {
      queuedWorkersPayload = data
      if (queuedWorkerUpdate) {
        return
      }
      queuedWorkerUpdate = true

      const flushWorkerUpdate = () => {
        queuedWorkerUpdate = false
        if (queuedWorkersPayload !== null) {
          updateWorkerProgressCharts(queuedWorkersPayload)
          queuedWorkersPayload = null
          lastWorkersUpdate.value = Date.now()
          workersStale.value = false
        }
      }

      if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(flushWorkerUpdate)
      } else {
        setTimeout(flushWorkerUpdate, 0)
      }
    }

    function updatePendingTasksList(data: PendingTasksMessage): void {
      const results: PendingTaskSummary[] = data.results.map((result) => ({
        id: result.id,
        priority: result.priority,
        label: result.label,
        status: result.status,
      }))
      pendingTasksData.value.taskList = results
      if (data.queue_eta) {
        queueEta.value = {
          formatted: formatDuration(data.queue_eta.eta_seconds),
          seconds: data.queue_eta.eta_seconds,
          confidence: data.queue_eta.confidence || 'low',
        }
      } else {
        queueEta.value = null
      }
    }

    function updateCompletedTasksList(data: CompletedTasksMessage): void {
      const results: CompletedTaskSummary[] = data.results.map((result) => ({
        id: result.id,
        label: result.label,
        dateTimeCompleted: dateTools.printDateTimeString(result.finish_time),
        dateTimeSinceCompleted: result.human_readable_time,
        success: result.success,
      }))
      completedTasksData.value.taskList = results
    }

    function initDashboardWebsocket() {
      ws = compressoWSHandler.init()
      let activeServerId: string | null = null

      compressoWSHandler.addEventListener('open', 'start_dashboard_messages', function (evt) {
        const activeSocket = evt.target instanceof WebSocket ? evt.target : ws
        if (!activeSocket) return
        activeSocket.send(JSON.stringify({ command: 'start_workers_info', params: {} }))
        activeSocket.send(JSON.stringify({ command: 'start_pending_tasks_info', params: {} }))
        activeSocket.send(JSON.stringify({ command: 'start_completed_tasks_info', params: {} }))
        startLiveMetrics(activeSocket)
      })

      compressoWSHandler.addEventListener('message', 'handle_dashboard_messages', function (evt) {
        if (typeof evt.data === 'string') {
          const jsonData = parseDashboardEnvelope(evt.data)
          if (jsonData?.success) {
            if (activeServerId === null) {
              activeServerId = jsonData.server_id
            } else {
              if (jsonData.server_id !== activeServerId) {
                log.debug('Compresso server has restarted. Reloading page...')
                location.reload()
              }
            }
            switch (jsonData.type) {
              case 'workers_info':
                queueWorkerProgressUpdate(jsonData.data)
                break
              case 'pending_tasks':
                updatePendingTasksList(jsonData.data)
                break
              case 'completed_tasks':
                updateCompletedTasksList(jsonData.data)
                break
              case 'system_status':
                updateLiveMetrics(jsonData.data)
                break
            }
          } else if (jsonData?.success === false) {
            log.error('WebSocket Error: Received contained errors - ' + evt.data)
          } else {
            log.error('WebSocket Error: Received an invalid dashboard message')
          }
        } else {
          log.error('WebSocket Error: Received data was not JSON - ' + evt.data)
        }
      })
    }

    function closeDashboardWebsocket() {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ command: 'stop_workers_info', params: {} }))
        ws.send(JSON.stringify({ command: 'stop_pending_tasks_info', params: {} }))
        ws.send(JSON.stringify({ command: 'stop_completed_tasks_info', params: {} }))
        stopLiveMetrics(ws)
      }
      compressoWSHandler.close()
    }

    async function fetchOptimizationProgress() {
      try {
        const response = await axios.get<ApiSchema<'OptimizationProgress'>>(
          getCompressoApiUrl('v2', 'compression/optimization-progress'),
        )
        optimizationData.value = {
          totalFiles: response.data.total_files || 0,
          processedFiles: response.data.processed_files || 0,
          percent: response.data.percent || 0,
          loading: false,
        }
      } catch (_e) {
        optimizationData.value.loading = false
      }
    }

    let staleCheckInterval: ReturnType<typeof setInterval> | null = null

    onMounted(() => {
      initDashboardWebsocket()
      fetchSystemInfo()
      fetchOptimizationProgress()
      staleCheckInterval = setInterval(() => {
        if (lastWorkersUpdate.value && Date.now() - lastWorkersUpdate.value > 10000) {
          workersStale.value = true
        }
      }, 2000)
    })

    onUnmounted(() => {
      closeDashboardWebsocket()
      if (staleCheckInterval) clearInterval(staleCheckInterval)
    })

    return {
      workerProgressList,
      pendingTasksData,
      completedTasksData,
      systemInfo,
      liveMetrics,
      gpuHistory,
      workersStale,
      optimizationData,
      queueEta,
    }
  },
  methods: {
    pauseAllWorkers: function () {
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'workers/worker/pause/all'),
        data: {},
      })
        .then(() => {
          this.$q.notify({
            color: 'positive',
            position: 'top',
            message: this.$t('components.workers.workerPaused'),
            icon: 'check_circle',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('components.workers.workerPausedFailed'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    resumeAllWorkers: function () {
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'workers/worker/resume/all'),
        data: {},
      })
        .then(() => {
          this.$q.notify({
            color: 'positive',
            position: 'top',
            message: this.$t('components.workers.workerResumed'),
            icon: 'check_circle',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('components.workers.workerResumedFailed'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    terminateWorker: function (workerId: string) {
      const data: ApiSchema<'RequestWorkerById'> = {
        worker_id: workerId,
      }
      axios({
        method: 'delete',
        url: getCompressoApiUrl('v2', 'workers/worker/terminate'),
        data: data,
      })
        .then(() => {
          this.$q.notify({
            color: 'positive',
            position: 'top',
            message: this.$t('components.workers.workerTerminated'),
            icon: 'check_circle',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('components.workers.workerTerminationFailed'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    terminateAllWorkers: function () {
      for (let key in this.workerProgressList) {
        const workerData = this.workerProgressList[key]
        if (!workerData) continue
        if (workerData.idle) {
          this.terminateWorker(workerData.id)
        } else {
          this.$q
            .dialog({
              title: this.$t('headers.confirm') + ' - ' + workerData.name,
              message: this.$t('components.workers.terminateWorkerWarning'),
              cancel: true,
              persistent: true,
            })
            .onOk(() => {
              this.terminateWorker(workerData.id)
            })
        }
      }
    },
  },
})
</script>
