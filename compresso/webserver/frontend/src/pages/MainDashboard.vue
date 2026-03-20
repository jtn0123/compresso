<template>
  <q-page padding>
    <div class="row q-col-gutter-md">

      <!-- Row 1: System Status Bar -->
      <div class="col-12">
        <SystemStatusBar :systemInfo="systemInfo" :liveMetrics="liveMetrics" />
      </div>

      <!-- Row 2: Hero section -->
      <!-- Left: Donut + Stats -->
      <div class="col-12 col-md-5 col-lg-4">
        <q-card flat bordered class="full-height">
          <q-card-section>
            <LibraryDonutChart
              :totalFiles="optimizationData.totalFiles"
              :processedFiles="optimizationData.processedFiles"
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
      <div class="col-12 col-md-7 col-lg-8">
        <WorkersPanel
          :workerProgressList="workerProgressList"
          @pause-all="pauseAllWorkers"
          @resume-all="resumeAllWorkers"
          @terminate-all="terminateAllWorkers"
        />

        <!-- Stale data warning -->
        <div v-if="workersStale" class="q-mt-sm">
          <q-banner dense class="bg-warning text-dark text-caption" rounded>
            <template v-slot:avatar>
              <q-icon name="warning" color="dark" />
            </template>
            {{ $t('common.dataStale') }}
          </q-banner>
        </div>
      </div>

      <!-- Row 3: Tasks -->
      <div class="col-12 col-md-6">
        <PendingTasks v-bind="pendingTasksData" />
      </div>
      <div class="col-12 col-md-6">
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

<script>
import SystemStatusBar from 'components/dashboard/SystemStatusBar.vue'
import LibraryDonutChart from 'components/charts/LibraryDonutChart.vue'
import CompactStatsGrid from 'components/dashboard/CompactStatsGrid.vue'
import WorkersPanel from 'components/dashboard/workers/WorkersPanel.vue'
import LinkedNodesPanel from 'components/dashboard/LinkedNodesPanel.vue'
import HealthCheckPanel from 'components/dashboard/HealthCheckPanel.vue'
import PendingTasks from 'components/dashboard/pending/PendingTasksDashboardSection.vue'
import CompletedTasks from "components/dashboard/completed/CompletedTasksDashboardSection.vue"
import dateTools from "src/js/dateTools"
import { useQuasar } from "quasar"
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from "vue-i18n"
import { CompressoWebsocketHandler } from "src/js/compressoWebsocket"
import axios from "axios"
import { getCompressoApiUrl } from "src/js/compressoGlobals"
import ReleaseNotesDialog from "components/docs/ReleaseNotesDialog.vue"
import { useWorkerGauges } from "src/composables/useWorkerGauges"
import { useSystemStatus } from "src/composables/useSystemStatus"

export default {
  name: 'MainDashboard',
  components: {
    ReleaseNotesDialog,
    CompletedTasks,
    SystemStatusBar,
    LibraryDonutChart,
    CompactStatsGrid,
    WorkersPanel,
    LinkedNodesPanel,
    HealthCheckPanel,
    PendingTasks
  },
  setup() {
    const { t: $t } = useI18n();
    const $q = useQuasar();
    const { generateGroupColour } = useWorkerGauges();
    const { systemInfo, liveMetrics, fetchSystemInfo, startLiveMetrics, updateLiveMetrics } = useSystemStatus();
    const lastWorkersUpdate = ref(null);
    const workersStale = ref(false);
    const workerProgressList = ref([]);
    const pendingTasksData = ref({
      taskList: []
    });
    const completedTasksData = ref({
      taskList: []
    });
    const optimizationData = ref({
      totalFiles: 0,
      processedFiles: 0,
      percent: 0,
      loading: true
    });

    let ws = null;
    let compressoWSHandler = CompressoWebsocketHandler($t);

    let workerGroupColours = {}

    function updateWorkerProgressCharts(data) {
      function calculateEtc(percent_completed, time_elapsed) {
        let percent_to_go = (100 - parseInt(percent_completed))
        return (parseInt(time_elapsed) / parseInt(percent_completed) * percent_to_go)
      }

      let workerData = {}
      for (let i = 0; i < data.length; i++) {
        let worker = data[i];

        // Set background colour
        let workerGroupColour;
        if (worker.name in workerGroupColours) {
          workerGroupColour = workerGroupColours[worker.name];
        } else {
          workerGroupColours[worker.name] = generateGroupColour(worker.name);
          workerGroupColour = workerGroupColours[worker.name];
        }

        // Set 'idle' status as defaults
        workerData['worker-' + worker.id] = {
          indeterminate: false,
          id: worker.id,
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
          workerGroupColour: workerGroupColour,
          workerType: '',
          currentFile: '',
          currentTask: null,
          runnersInfo: {},
          subprocess: {},
        }
        workerData['worker-' + worker.id].currentFile = worker.current_file || '';
        workerData['worker-' + worker.id].currentTask = worker.current_task ?? null;
        workerData['worker-' + worker.id].runnersInfo = worker.runners_info || {};
        workerData['worker-' + worker.id].subprocess = worker.subprocess || {};

        if (worker.paused) {
          workerData['worker-' + worker.id].label = worker.name;
          workerData['worker-' + worker.id].color = 'negative';
          workerData['worker-' + worker.id].progressText = '...';
          workerData['worker-' + worker.id].state = $t('components.workers.state.paused');
        }
        if (!worker.idle) {
          workerData['worker-' + worker.id].label = worker.name + ': ' + worker.current_file;
          workerData['worker-' + worker.id].color = 'secondary';
          workerData['worker-' + worker.id].state = $t('components.workers.state.processing');

          let currentRunner = $t('components.workers.currentRunner.indeterminate');
          if (typeof worker.runners_info === 'object' && worker.runners_info !== null) {
            for (const [runnerKey, runnerValue] of Object.entries(worker.runners_info)) {
              if (runnerValue.status === 'in_progress') {
                currentRunner = runnerValue.name;
              }
            }
          }
          workerData['worker-' + worker.id].currentRunner = currentRunner;

          const processingDuration = (new Date() - new Date(worker.start_time * 1000)) / 1000;
          workerData['worker-' + worker.id].startTime = dateTools.printDateTimeString(worker.start_time);
          workerData['worker-' + worker.id].timeSinceStart = dateTools.printSecondsAsDuration(processingDuration);
          workerData['worker-' + worker.id].currentCommand = worker.current_command;
          workerData['worker-' + worker.id].workerLog = worker.worker_log_tail;

          const percentValue = Number(worker.subprocess?.percent);
          const elapsedValue = Number(worker.subprocess?.elapsed);
          const hasPercent = Number.isFinite(percentValue) && worker.subprocess?.percent !== '';
          const hasElapsed = Number.isFinite(elapsedValue) && elapsedValue >= 0;
          const canEstimate = hasPercent && percentValue > 0 && hasElapsed;

          if (hasPercent) {
            workerData['worker-' + worker.id].progress = percentValue;
            workerData['worker-' + worker.id].progressText = worker.subprocess.percent + '%';
          } else {
            workerData['worker-' + worker.id].indeterminate = true;
            workerData['worker-' + worker.id].progressText = '...';
          }

          if (canEstimate) {
            workerData['worker-' + worker.id].elapsed = dateTools.printSecondsAsDuration(elapsedValue);
            const etcDuration = calculateEtc(percentValue, elapsedValue);
            workerData['worker-' + worker.id].etc = dateTools.printSecondsAsDuration(etcDuration);
          } else {
            workerData['worker-' + worker.id].elapsed = '';
            workerData['worker-' + worker.id].etc = '...';
          }

          if (worker.paused) {
            workerData['worker-' + worker.id].indeterminate = true;
            workerData['worker-' + worker.id].color = 'negative';
            workerData['worker-' + worker.id].state = $t('components.workers.state.paused');
          }
        }
      }
      workerProgressList.value = workerData;
    }

    function updatePendingTasksList(data) {
      let result;
      let results = [];
      for (let i = 0; i < data.results.length; i++) {
        result = data.results[i];
        results[i] = {
          id: data.results[i].id,
          priority: data.results[i].priority,
          label: data.results[i].label,
          status: data.results[i].status,
        }
      }
      pendingTasksData.value.taskList = results;
    }

    function updateCompletedTasksList(data) {
      let result;
      let results = [];
      for (let i = 0; i < data.results.length; i++) {
        result = data.results[i];
        results[i] = {
          id: data.results[i].id,
          label: data.results[i].label,
          dateTimeCompleted: dateTools.printDateTimeString(data.results[i].finish_time),
          dateTimeSinceCompleted: data.results[i].human_readable_time,
          success: data.results[i].success,
        }
      }
      completedTasksData.value.taskList = results;
    }

    function initDashboardWebsocket() {
      ws = compressoWSHandler.init();
      let serverId = compressoWSHandler.serverId;

      compressoWSHandler.addEventListener('open', 'start_dashboard_messages', function (evt) {
        ws.send(JSON.stringify({ command: 'start_workers_info', params: {} }));
        ws.send(JSON.stringify({ command: 'start_pending_tasks_info', params: {} }));
        ws.send(JSON.stringify({ command: 'start_completed_tasks_info', params: {} }));
        startLiveMetrics(ws);
      });

      compressoWSHandler.addEventListener('message', 'handle_dashboard_messages', function (evt) {
        if (typeof evt.data === 'string') {
          let jsonData = JSON.parse(evt.data);
          if (jsonData.success) {
            if (serverId === null) {
              serverId = jsonData.server_id;
            } else {
              if (jsonData.server_id !== serverId) {
                console.debug('Compresso server has restarted. Reloading page...');
                location.reload();
              }
            }
            switch (jsonData.type) {
              case 'workers_info':
                updateWorkerProgressCharts(jsonData.data);
                lastWorkersUpdate.value = Date.now();
                workersStale.value = false;
                break;
              case 'pending_tasks':
                updatePendingTasksList(jsonData.data);
                break;
              case 'completed_tasks':
                updateCompletedTasksList(jsonData.data);
                break;
              case 'system_status':
                updateLiveMetrics(jsonData.data);
                break;
            }
          } else {
            console.error('WebSocket Error: Received contained errors - ' + evt.data);
          }
        } else {
          console.error('WebSocket Error: Received data was not JSON - ' + evt.data);
        }
      });
    }

    function closeDashboardWebsocket() {
      compressoWSHandler.close();
    }

    async function fetchOptimizationProgress() {
      try {
        const response = await axios.get(getCompressoApiUrl('v2', 'compression/optimization-progress'));
        optimizationData.value = {
          totalFiles: response.data.total || 0,
          processedFiles: response.data.processed || 0,
          percent: response.data.percent || 0,
          loading: false
        };
      } catch (_e) {
        optimizationData.value.loading = false;
      }
    }

    let staleCheckInterval = null;

    onMounted(() => {
      initDashboardWebsocket();
      fetchSystemInfo();
      fetchOptimizationProgress();
      staleCheckInterval = setInterval(() => {
        if (lastWorkersUpdate.value && (Date.now() - lastWorkersUpdate.value) > 10000) {
          workersStale.value = true;
        }
      }, 2000);
    })

    onUnmounted(() => {
      closeDashboardWebsocket();
      if (staleCheckInterval) clearInterval(staleCheckInterval);
    })

    return {
      workerProgressList,
      pendingTasksData,
      completedTasksData,
      systemInfo,
      liveMetrics,
      workersStale,
      optimizationData,
    }
  },
  methods: {
    pauseAllWorkers: function () {
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'workers/worker/pause/all'),
        data: {}
      }).then((response) => {
        this.$q.notify({
          color: 'positive',
          position: 'top',
          message: this.$t('components.workers.workerPaused'),
          icon: 'check_circle',
          actions: [{ icon: 'close', color: 'white' }]
        })
      }).catch(() => {
        this.$q.notify({
          color: 'negative',
          position: 'top',
          message: this.$t('components.workers.workerPausedFailed'),
          icon: 'report_problem',
          actions: [{ icon: 'close', color: 'white' }]
        })
      })
    },
    resumeAllWorkers: function () {
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'workers/worker/resume/all'),
        data: {}
      }).then((response) => {
        this.$q.notify({
          color: 'positive',
          position: 'top',
          message: this.$t('components.workers.workerResumed'),
          icon: 'check_circle',
          actions: [{ icon: 'close', color: 'white' }]
        })
      }).catch(() => {
        this.$q.notify({
          color: 'negative',
          position: 'top',
          message: this.$t('components.workers.workerResumedFailed'),
          icon: 'report_problem',
          actions: [{ icon: 'close', color: 'white' }]
        })
      })
    },
    terminateWorker: function (workerId) {
      let data = {
        worker_id: workerId,
      }
      axios({
        method: 'delete',
        url: getCompressoApiUrl('v2', 'workers/worker/terminate'),
        data: data
      }).then((response) => {
        this.$q.notify({
          color: 'positive',
          position: 'top',
          message: this.$t('components.workers.workerTerminated'),
          icon: 'check_circle',
          actions: [{ icon: 'close', color: 'white' }]
        })
      }).catch(() => {
        this.$q.notify({
          color: 'negative',
          position: 'top',
          message: this.$t('components.workers.workerTerminationFailed'),
          icon: 'report_problem',
          actions: [{ icon: 'close', color: 'white' }]
        })
      })
    },
    terminateAllWorkers: function () {
      for (let key in this.workerProgressList) {
        let workerData = this.workerProgressList[key];
        if (workerData.idle) {
          this.terminateWorker(workerData.id);
        } else {
          this.$q.dialog({
            title: this.$t('headers.confirm') + ' - ' + workerData.name,
            message: this.$t('components.workers.terminateWorkerWarning'),
            cancel: true,
            persistent: true
          }).onOk(() => {
            this.terminateWorker(workerData.id);
          })
        }
      }
    }
  }
}
</script>
