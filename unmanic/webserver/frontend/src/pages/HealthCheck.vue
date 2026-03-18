<template>
  <q-page padding>
    <div class="q-pa-md">
      <div class="text-h5 q-mb-md">Health Check</div>

      <!-- Summary Cards -->
      <div class="row q-col-gutter-md q-mb-lg">
        <div class="col-6 col-sm">
          <q-card class="bg-positive text-white">
            <q-card-section>
              <div class="text-caption">Healthy</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.healthy }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-6 col-sm">
          <q-card class="bg-warning text-white">
            <q-card-section>
              <div class="text-caption">Warning</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.warning }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-6 col-sm">
          <q-card class="bg-negative text-white">
            <q-card-section>
              <div class="text-caption">Corrupted</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.corrupted }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-6 col-sm">
          <q-card class="bg-grey text-white">
            <q-card-section>
              <div class="text-caption">Unchecked</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.unchecked }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-6 col-sm">
          <q-card class="bg-info text-white">
            <q-card-section>
              <div class="text-caption">Total</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.total }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Scan Controls -->
      <q-card class="q-mb-lg">
        <q-card-section>
          <div class="text-h6 q-mb-md">Scan Controls</div>
          <div class="row q-col-gutter-md items-end">
            <div class="col-12 col-sm-4">
              <q-select
                v-model="selectedLibraryId"
                :options="libraryOptions"
                label="Library"
                outlined
                dense
                emit-value
                map-options
              />
            </div>
            <div class="col-12 col-sm-3">
              <q-select
                v-model="scanMode"
                :options="[{label: 'Quick (ffprobe)', value: 'quick'}, {label: 'Thorough (full decode)', value: 'thorough'}]"
                label="Mode"
                outlined
                dense
                emit-value
                map-options
              />
            </div>
            <div class="col-12 col-sm-5">
              <q-btn
                color="primary"
                label="Scan Library"
                :loading="scanning"
                :disable="scanning"
                @click="scanLibrary"
                class="q-mr-sm"
              />
              <q-btn
                v-if="scanning"
                color="negative"
                label="Cancel Scan"
                outline
                @click="cancelScan"
              />
            </div>
          </div>

          <!-- Worker Controls -->
          <div class="row q-col-gutter-md items-center q-mt-sm">
            <div class="col-auto">
              <span class="text-subtitle2">Workers:</span>
            </div>
            <div class="col-auto">
              <q-btn
                flat round dense
                icon="remove"
                size="sm"
                :disable="workerCount <= 1"
                @click="changeWorkerCount(-1)"
              />
            </div>
            <div class="col-auto">
              <span class="text-h6">{{ workerCount }}</span>
            </div>
            <div class="col-auto">
              <q-btn
                flat round dense
                icon="add"
                size="sm"
                :disable="workerCount >= 16"
                @click="changeWorkerCount(1)"
              />
            </div>
          </div>

          <!-- Scan Progress Panel -->
          <div v-if="scanning" class="q-mt-md">
            <div class="row items-center q-mb-sm">
              <div class="col">
                <q-linear-progress
                  :value="scanProgressPercent"
                  color="primary"
                  size="20px"
                  rounded
                >
                  <div class="absolute-full flex flex-center">
                    <span class="text-white text-caption" style="text-shadow: 0 0 3px rgba(0,0,0,0.5)">
                      {{ scanProgress.checked }} / {{ scanProgress.total }}
                      ({{ Math.round(scanProgressPercent * 100) }}%)
                    </span>
                  </div>
                </q-linear-progress>
              </div>
            </div>
            <div class="row q-col-gutter-md q-mb-sm">
              <div class="col-auto">
                <span class="text-caption">
                  Speed: {{ scanProgress.files_per_second || 0 }} files/sec
                </span>
              </div>
              <div class="col-auto">
                <span class="text-caption">
                  ETA: {{ formatEta(scanProgress.eta_seconds) }}
                </span>
              </div>
            </div>
            <!-- Per-worker status -->
            <div v-if="scanProgress.workers && Object.keys(scanProgress.workers).length > 0" class="q-mt-sm">
              <div class="text-caption q-mb-xs">Worker Status:</div>
              <div v-for="(worker, wid) in scanProgress.workers" :key="wid" class="row items-center q-mb-xs">
                <q-icon
                  :name="worker.status === 'checking' ? 'circle' : 'circle'"
                  :color="worker.status === 'checking' ? 'positive' : 'grey'"
                  size="xs"
                  class="q-mr-sm"
                />
                <span class="text-caption">
                  Worker {{ wid }}:
                  <span v-if="worker.status === 'checking'">{{ truncateFilename(worker.current_file) }}</span>
                  <span v-else class="text-grey">idle</span>
                </span>
              </div>
            </div>
          </div>

          <!-- Single file check -->
          <div class="row q-col-gutter-md items-end q-mt-md">
            <div class="col-12 col-sm-8">
              <q-input
                v-model="singleFilePath"
                label="Check Single File"
                placeholder="/path/to/video.mkv"
                outlined
                dense
              />
            </div>
            <div class="col-12 col-sm-4">
              <q-btn
                color="secondary"
                label="Check File"
                :disable="!singleFilePath"
                @click="checkSingleFile"
              />
            </div>
          </div>

          <!-- Single file result -->
          <div v-if="singleFileResult" class="q-mt-md">
            <q-banner :class="singleFileResult.status === 'healthy' ? 'bg-positive text-white' : singleFileResult.status === 'warning' ? 'bg-warning text-white' : 'bg-negative text-white'">
              <strong>{{ singleFileResult.abspath }}</strong>: {{ singleFileResult.status }}
              <span v-if="singleFileResult.error_detail"> — {{ singleFileResult.error_detail }}</span>
            </q-banner>
          </div>
        </q-card-section>
      </q-card>

      <!-- Status Table -->
      <q-card>
        <q-card-section>
          <div class="text-h6">File Status</div>
        </q-card-section>
        <q-card-section>
          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12 col-sm-6">
              <q-input
                v-model="searchValue"
                debounce="500"
                placeholder="Search files..."
                dense
                outlined
                @update:model-value="loadStatuses"
              >
                <template v-slot:prepend>
                  <q-icon name="search" />
                </template>
              </q-input>
            </div>
            <div class="col-12 col-sm-3">
              <q-select
                v-model="statusFilter"
                :options="[{label: 'All', value: null}, {label: 'Healthy', value: 'healthy'}, {label: 'Warning', value: 'warning'}, {label: 'Corrupted', value: 'corrupted'}, {label: 'Unchecked', value: 'unchecked'}]"
                label="Status Filter"
                dense
                outlined
                emit-value
                map-options
                @update:model-value="loadStatuses"
              />
            </div>
          </div>

          <div style="overflow-x: auto">
          <q-table
            :rows="statusResults"
            :columns="statusColumns"
            row-key="id"
            flat
            dense
            :loading="loadingStatuses"
            :pagination="pagination"
            @request="onTableRequest"
            no-data-label="No files match your filters"
          >
            <template v-slot:body-cell-status="props">
              <q-td :props="props">
                <q-badge
                  :color="getStatusColor(props.row.status)"
                >
                  {{ props.row.status }}
                </q-badge>
              </q-td>
            </template>
            <template v-slot:body-cell-actions="props">
              <q-td :props="props">
                <q-btn
                  flat
                  round
                  dense
                  icon="refresh"
                  size="sm"
                  @click="recheckFile(props.row)"
                  :loading="props.row._checking"
                />
                <q-btn
                  flat
                  round
                  dense
                  icon="info"
                  size="sm"
                  @click="showFileInfo(props.row.abspath)"
                />
              </q-td>
            </template>
          </q-table>
          </div>
        </q-card-section>
      </q-card>

      <FileInfoDialog ref="fileInfoDialogRef" />
    </div>
  </q-page>
</template>

<script>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { useQuasar } from 'quasar';
import axios from 'axios';
import { getUnmanicApiUrl } from 'src/js/unmanicGlobals';
import FileInfoDialog from 'components/fileinfo/FileInfoDialog.vue';

export default {
  name: 'HealthCheck',
  components: { FileInfoDialog },
  setup() {
    const $q = useQuasar();
    const loadingSummary = ref(true);
    const summary = ref({ healthy: 0, warning: 0, corrupted: 0, unchecked: 0, checking: 0, total: 0 });
    const scanning = ref(false);
    const scanProgress = ref({ total: 0, checked: 0, workers: {}, files_per_second: 0, eta_seconds: 0 });
    const workerCount = ref(1);
    const scanProgressPercent = ref(0);
    const selectedLibraryId = ref(1);
    const scanMode = ref('quick');
    const libraryOptions = ref([{ label: 'Default Library', value: 1 }]);
    const singleFilePath = ref('');
    const singleFileResult = ref(null);
    const searchValue = ref('');
    const statusFilter = ref(null);
    const statusResults = ref([]);
    const loadingStatuses = ref(false);
    const fileInfoDialogRef = ref(null);
    let pollTimer = null;

    const pagination = ref({
      page: 1,
      rowsPerPage: 20,
      rowsNumber: 0,
      sortBy: 'last_checked',
      descending: true,
    });

    const statusColumns = [
      { name: 'abspath', label: 'File Path', field: 'abspath', align: 'left', sortable: true },
      { name: 'status', label: 'Status', field: 'status', align: 'center', sortable: true },
      { name: 'check_mode', label: 'Mode', field: 'check_mode', align: 'center' },
      { name: 'error_detail', label: 'Error Detail', field: 'error_detail', align: 'left' },
      { name: 'last_checked', label: 'Last Checked', field: 'last_checked', align: 'left', sortable: true },
      { name: 'error_count', label: 'Errors', field: 'error_count', align: 'center' },
      { name: 'actions', label: 'Actions', field: 'actions', align: 'center' },
    ];

    function getStatusColor(status) {
      if (status === 'healthy') return 'positive';
      if (status === 'warning') return 'warning';
      if (status === 'corrupted') return 'negative';
      if (status === 'checking') return 'info';
      return 'grey';
    }

    async function loadSummary() {
      try {
        const url = selectedLibraryId.value
          ? getUnmanicApiUrl('v2', 'healthcheck/summary') + '?library_id=' + selectedLibraryId.value
          : getUnmanicApiUrl('v2', 'healthcheck/summary');
        const response = await axios.get(url);
        if (response.data) {
          summary.value = response.data;
          scanning.value = response.data.scanning || false;
          if (response.data.scan_progress) {
            scanProgress.value = response.data.scan_progress;
            const total = response.data.scan_progress.total || 0;
            const checked = response.data.scan_progress.checked || 0;
            scanProgressPercent.value = total > 0 ? checked / total : 0;
          }
        }
      } catch (error) {
        console.error('Error loading health summary:', error);
        $q.notify({ type: 'negative', message: 'Failed to load health summary' });
      } finally {
        loadingSummary.value = false;
      }
    }

    async function loadWorkerInfo() {
      try {
        const response = await axios.get(getUnmanicApiUrl('v2', 'healthcheck/workers'));
        if (response.data) {
          workerCount.value = response.data.worker_count || 1;
          if (response.data.scan_progress) {
            scanProgress.value = response.data.scan_progress;
            const total = response.data.scan_progress.total || 0;
            const checked = response.data.scan_progress.checked || 0;
            scanProgressPercent.value = total > 0 ? checked / total : 0;
          }
        }
      } catch (error) {
        console.error('Error loading worker info:', error);
        $q.notify({ type: 'negative', message: 'Failed to load worker info' });
      }
    }

    async function changeWorkerCount(delta) {
      const newCount = workerCount.value + delta;
      if (newCount < 1 || newCount > 16) return;
      try {
        const response = await axios.post(getUnmanicApiUrl('v2', 'healthcheck/workers'), {
          worker_count: newCount,
        });
        if (response.data) {
          workerCount.value = response.data.worker_count || newCount;
        }
      } catch (error) {
        console.error('Error setting worker count:', error);
        $q.notify({ type: 'negative', message: 'Failed to update worker count' });
      }
    }

    function formatEta(seconds) {
      if (!seconds || seconds <= 0) return '--';
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = seconds % 60;
      if (h > 0) return h + 'h ' + m + 'm';
      if (m > 0) return m + 'm ' + s + 's';
      return s + 's';
    }

    function truncateFilename(filepath) {
      if (!filepath) return '';
      const parts = filepath.split('/');
      const name = parts[parts.length - 1];
      return name.length > 50 ? name.substring(0, 47) + '...' : name;
    }

    async function loadStatuses() {
      loadingStatuses.value = true;
      try {
        const start = (pagination.value.page - 1) * pagination.value.rowsPerPage;
        const response = await axios.post(getUnmanicApiUrl('v2', 'healthcheck/status'), {
          start: start,
          length: pagination.value.rowsPerPage,
          search_value: searchValue.value,
          library_id: selectedLibraryId.value,
          status_filter: statusFilter.value,
          order_by: pagination.value.sortBy || 'last_checked',
          order_direction: pagination.value.descending ? 'desc' : 'asc',
        });
        if (response.data) {
          statusResults.value = (response.data.results || []).map(r => ({ ...r, _checking: false }));
          pagination.value.rowsNumber = response.data.recordsFiltered || 0;
        }
      } catch (error) {
        console.error('Error loading health statuses:', error);
        $q.notify({ type: 'negative', message: 'Failed to load health statuses' });
      } finally {
        loadingStatuses.value = false;
      }
    }

    function scanLibrary() {
      $q.dialog({
        title: 'Start Library Scan?',
        message: 'This will scan all media files in the selected library. On large libraries this may take a long time.',
        cancel: true,
        persistent: false,
      }).onOk(async () => {
        try {
          const response = await axios.post(getUnmanicApiUrl('v2', 'healthcheck/scan-library'), {
            library_id: selectedLibraryId.value,
            mode: scanMode.value,
          });
          if (response.data) {
            scanning.value = response.data.started;
            if (response.data.started) {
              startPolling();
              $q.notify({ type: 'positive', message: 'Library scan started' });
            } else {
              $q.notify({ type: 'warning', message: response.data.message || 'A scan is already in progress' });
            }
          }
        } catch (error) {
          console.error('Error starting library scan:', error);
          $q.notify({ type: 'negative', message: 'Failed to start library scan' });
        }
      });
    }

    async function cancelScan() {
      try {
        await axios.post(getUnmanicApiUrl('v2', 'healthcheck/cancel-scan'));
        $q.notify({ type: 'info', message: 'Scan cancellation requested' });
      } catch (error) {
        console.error('Error cancelling scan:', error);
        $q.notify({ type: 'negative', message: 'Failed to cancel scan' });
      }
    }

    async function checkSingleFile() {
      singleFileResult.value = null;
      try {
        const response = await axios.post(getUnmanicApiUrl('v2', 'healthcheck/scan'), {
          file_path: singleFilePath.value,
          library_id: selectedLibraryId.value,
          mode: scanMode.value,
        });
        if (response.data) {
          singleFileResult.value = response.data;
          await loadSummary();
          await loadStatuses();
        }
      } catch (error) {
        console.error('Error checking file:', error);
        $q.notify({ type: 'negative', message: 'Failed to check file' });
      }
    }

    async function recheckFile(row) {
      row._checking = true;
      try {
        await axios.post(getUnmanicApiUrl('v2', 'healthcheck/scan'), {
          file_path: row.abspath,
          library_id: row.library_id || selectedLibraryId.value,
          mode: scanMode.value,
        });
        await loadSummary();
        await loadStatuses();
      } catch (error) {
        console.error('Error re-checking file:', error);
        $q.notify({ type: 'negative', message: 'Failed to re-check file' });
      } finally {
        row._checking = false;
      }
    }

    function showFileInfo(filePath) {
      if (fileInfoDialogRef.value) {
        fileInfoDialogRef.value.probeByPath(filePath);
      }
    }

    function onTableRequest(props) {
      const { page, rowsPerPage, sortBy, descending } = props.pagination;
      pagination.value.page = page;
      pagination.value.rowsPerPage = rowsPerPage;
      pagination.value.sortBy = sortBy;
      pagination.value.descending = descending;
      loadStatuses();
    }

    let pollCount = 0;
    function getPollInterval() {
      if (pollCount > 20) return 15000;
      if (pollCount > 10) return 5000;
      return 2000;
    }

    function startPolling() {
      stopPolling();
      pollCount = 0;
      function doPoll() {
        pollTimer = setTimeout(async () => {
          pollCount++;
          await Promise.all([loadSummary(), loadWorkerInfo()]);
          if (!scanning.value) {
            stopPolling();
            await loadStatuses();
          } else {
            doPoll();
          }
        }, getPollInterval());
      }
      doPoll();
    }

    function stopPolling() {
      if (pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
      }
    }

    async function loadLibraries() {
      try {
        const response = await axios.get(getUnmanicApiUrl('v2', 'settings/read'));
        if (response.data && response.data.settings) {
          const libs = response.data.settings.libraries || [];
          if (libs.length > 0) {
            libraryOptions.value = libs.map(lib => ({
              label: lib.name || `Library ${lib.id}`,
              value: lib.id,
            }));
            selectedLibraryId.value = libs[0].id;
          }
        }
      } catch (error) {
        console.error('Error loading libraries:', error);
        $q.notify({ type: 'negative', message: 'Failed to load libraries' });
      }
    }

    watch(() => selectedLibraryId.value, () => {
      pagination.value.page = 1;
      loadStatuses();
      loadSummary();
    });

    onMounted(async () => {
      await loadLibraries();
      await Promise.all([loadSummary(), loadStatuses()]);
      if (scanning.value) startPolling();
    });

    onBeforeUnmount(() => {
      stopPolling();
    });

    return {
      summary,
      scanning,
      scanProgress,
      scanProgressPercent,
      workerCount,
      selectedLibraryId,
      scanMode,
      libraryOptions,
      singleFilePath,
      singleFileResult,
      searchValue,
      statusFilter,
      statusResults,
      loadingStatuses,
      loadingSummary,
      pagination,
      statusColumns,
      fileInfoDialogRef,
      getStatusColor,
      loadStatuses,
      scanLibrary,
      cancelScan,
      checkSingleFile,
      recheckFile,
      showFileInfo,
      onTableRequest,
      changeWorkerCount,
      formatEta,
      truncateFilename,
    };
  },
};
</script>
