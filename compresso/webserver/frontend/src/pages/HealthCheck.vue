<template>
  <q-page padding>
    <div class="q-pa-md">
      <PageHeader :title="$t('pages.healthCheck.title')" />

      <AdmonitionBanner type="tip" class="q-mb-md">
        {{ $t('pages.healthCheck.bannerText') }}
      </AdmonitionBanner>

      <!-- Summary Cards -->
      <div class="row q-col-gutter-md q-mb-lg">
        <div class="col-6 col-sm">
          <q-card flat bordered class="stat-card stat-card--positive">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.healthCheck.summaryHealthy') }}</div>
              <div class="stat-value">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.healthy }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-6 col-sm">
          <q-card flat bordered class="stat-card stat-card--warning">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.healthCheck.summaryWarning') }}</div>
              <div class="stat-value">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.warning }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-6 col-sm">
          <q-card flat bordered class="stat-card stat-card--negative">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.healthCheck.summaryCorrupted') }}</div>
              <div class="stat-value">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.corrupted }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-6 col-sm">
          <q-card flat bordered class="stat-card stat-card--grey">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.healthCheck.summaryUnchecked') }}</div>
              <div class="stat-value">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.unchecked }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-6 col-sm">
          <q-card flat bordered class="stat-card stat-card--info">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.healthCheck.summaryTotal') }}</div>
              <div class="stat-value">
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
          <div class="text-h6 q-mb-md">{{ $t('pages.healthCheck.scanControls') }}</div>
          <div class="row q-col-gutter-md items-end">
            <div class="col-12 col-sm-4">
              <q-select
                v-model="selectedLibraryId"
                :options="libraryOptions"
                :label="$t('pages.healthCheck.libraryLabel')"
                outlined
                dense
                emit-value
                map-options
              />
            </div>
            <div class="col-12 col-sm-3">
              <q-select
                v-model="scanMode"
                :options="scanModeOptions"
                :label="$t('pages.healthCheck.modeLabel')"
                outlined
                dense
                emit-value
                map-options
              />
            </div>
            <div class="col-12 col-sm-5">
              <q-btn
                color="primary"
                :label="$t('pages.healthCheck.scanLibrary')"
                :loading="scanning"
                :disable="scanning"
                @click="scanLibrary"
                class="q-mr-sm"
              />
              <q-btn
                v-if="scanning"
                color="negative"
                :label="$t('pages.healthCheck.cancelScan')"
                outline
                @click="cancelScan"
              />
            </div>
          </div>

          <!-- Worker Controls -->
          <div class="row q-col-gutter-md items-center q-mt-sm">
            <div class="col-auto">
              <span class="text-subtitle2">{{ $t('pages.healthCheck.workersLabel') }}</span>
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
                  {{ $t('pages.healthCheck.speedLabel') }} {{ scanProgress.files_per_second || 0 }} {{ $t('pages.healthCheck.filesPerSec') }}
                </span>
              </div>
              <div class="col-auto">
                <span class="text-caption">
                  {{ $t('pages.healthCheck.etaLabel') }} {{ formatEta(scanProgress.eta_seconds) }}
                </span>
              </div>
            </div>
            <!-- Per-worker status -->
            <div v-if="scanProgress.workers && Object.keys(scanProgress.workers).length > 0" class="q-mt-sm">
              <div class="text-caption q-mb-xs">{{ $t('pages.healthCheck.workerStatusLabel') }}</div>
              <div v-for="(worker, wid) in scanProgress.workers" :key="wid" class="row items-center q-mb-xs">
                <q-icon
                  :name="worker.status === 'checking' ? 'circle' : 'circle'"
                  :color="worker.status === 'checking' ? 'positive' : 'grey'"
                  size="xs"
                  class="q-mr-sm"
                />
                <span class="text-caption">
                  {{ $t('pages.healthCheck.workerIdLabel', { id: wid }) }}
                  <span v-if="worker.status === 'checking'">{{ truncateFilename(worker.current_file) }}</span>
                  <span v-else class="text-grey">{{ $t('pages.healthCheck.workerIdle') }}</span>
                </span>
              </div>
            </div>
          </div>

          <!-- Single file check -->
          <div class="row q-col-gutter-md items-end q-mt-md">
            <div class="col-12 col-sm-8">
              <q-input
                v-model="singleFilePath"
                :label="$t('pages.healthCheck.checkSingleFile')"
                :placeholder="$t('pages.healthCheck.singleFilePlaceholder')"
                outlined
                dense
              />
            </div>
            <div class="col-12 col-sm-4">
              <q-btn
                color="secondary"
                :label="$t('pages.healthCheck.checkFileButton')"
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
          <div class="text-h6">{{ $t('pages.healthCheck.fileStatus') }}</div>
        </q-card-section>
        <q-card-section>
          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12 col-sm-6">
              <q-input
                v-model="searchValue"
                debounce="500"
                :placeholder="$t('pages.healthCheck.searchPlaceholder')"
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
                :options="statusFilterOptions"
                :label="$t('pages.healthCheck.statusFilterLabel')"
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
            :no-data-label="$t('pages.healthCheck.noFilesMatch')"
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
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';
import axios from 'axios';
import { getCompressoApiUrl } from 'src/js/compressoGlobals';
import { createLogger } from 'src/composables/useLogger';
import FileInfoDialog from 'components/fileinfo/FileInfoDialog.vue';
import AdmonitionBanner from 'components/ui/AdmonitionBanner.vue';
import PageHeader from 'components/ui/PageHeader.vue';

export default {
  name: 'HealthCheck',
  components: { FileInfoDialog, AdmonitionBanner, PageHeader },
  setup() {
    const $q = useQuasar();
    const { t } = useI18n();
    const log = createLogger('HealthCheck');
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

    const statusColumns = computed(() => [
      { name: 'abspath', label: t('pages.healthCheck.columnFilePath'), field: 'abspath', align: 'left', sortable: true },
      { name: 'status', label: t('pages.healthCheck.columnStatus'), field: 'status', align: 'center', sortable: true },
      { name: 'check_mode', label: t('pages.healthCheck.columnMode'), field: 'check_mode', align: 'center' },
      { name: 'error_detail', label: t('pages.healthCheck.columnErrorDetail'), field: 'error_detail', align: 'left' },
      { name: 'last_checked', label: t('pages.healthCheck.columnLastChecked'), field: 'last_checked', align: 'left', sortable: true },
      { name: 'error_count', label: t('pages.healthCheck.columnErrors'), field: 'error_count', align: 'center' },
      { name: 'actions', label: t('pages.healthCheck.columnActions'), field: 'actions', align: 'center' },
    ]);

    const scanModeOptions = computed(() => [
      { label: t('pages.healthCheck.modeQuick'), value: 'quick' },
      { label: t('pages.healthCheck.modeThorough'), value: 'thorough' },
    ]);

    const statusFilterOptions = computed(() => [
      { label: t('pages.healthCheck.filterAll'), value: null },
      { label: t('pages.healthCheck.filterHealthy'), value: 'healthy' },
      { label: t('pages.healthCheck.filterWarning'), value: 'warning' },
      { label: t('pages.healthCheck.filterCorrupted'), value: 'corrupted' },
      { label: t('pages.healthCheck.filterUnchecked'), value: 'unchecked' },
    ]);

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
          ? getCompressoApiUrl('v2', 'healthcheck/summary') + '?library_id=' + selectedLibraryId.value
          : getCompressoApiUrl('v2', 'healthcheck/summary');
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
        log.error('Error loading health summary: ' + error);
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedLoadSummary') });
      } finally {
        loadingSummary.value = false;
      }
    }

    async function loadWorkerInfo() {
      try {
        const response = await axios.get(getCompressoApiUrl('v2', 'healthcheck/workers'));
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
        log.error('Error loading worker info: ' + error);
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedLoadWorkerInfo') });
      }
    }

    async function changeWorkerCount(delta) {
      const newCount = workerCount.value + delta;
      if (newCount < 1 || newCount > 16) return;
      try {
        const response = await axios.post(getCompressoApiUrl('v2', 'healthcheck/workers'), {
          worker_count: newCount,
        });
        if (response.data) {
          workerCount.value = response.data.worker_count || newCount;
        }
      } catch (error) {
        log.error('Error setting worker count: ' + error);
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedUpdateWorkerCount') });
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
        const response = await axios.post(getCompressoApiUrl('v2', 'healthcheck/status'), {
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
        log.error('Error loading health statuses: ' + error);
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedLoadStatuses') });
      } finally {
        loadingStatuses.value = false;
      }
    }

    function scanLibrary() {
      $q.dialog({
        title: t('pages.healthCheck.startScanTitle'),
        message: t('pages.healthCheck.startScanMessage'),
        cancel: true,
        persistent: false,
      }).onOk(async () => {
        try {
          const response = await axios.post(getCompressoApiUrl('v2', 'healthcheck/scan-library'), {
            library_id: selectedLibraryId.value,
            mode: scanMode.value,
          });
          if (response.data) {
            scanning.value = response.data.started;
            if (response.data.started) {
              startPolling();
              $q.notify({ type: 'positive', message: t('pages.healthCheck.scanStarted') });
            } else {
              $q.notify({ type: 'warning', message: response.data.message || t('pages.healthCheck.scanAlreadyInProgress') });
            }
          }
        } catch (error) {
          log.error('Error starting library scan: ' + error);
          $q.notify({ type: 'negative', message: t('pages.healthCheck.failedStartScan') });
        }
      });
    }

    async function cancelScan() {
      try {
        await axios.post(getCompressoApiUrl('v2', 'healthcheck/cancel-scan'));
        $q.notify({ type: 'info', message: t('pages.healthCheck.scanCancelRequested') });
      } catch (error) {
        log.error('Error cancelling scan: ' + error);
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedCancelScan') });
      }
    }

    async function checkSingleFile() {
      singleFileResult.value = null;
      try {
        const response = await axios.post(getCompressoApiUrl('v2', 'healthcheck/scan'), {
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
        log.error('Error checking file: ' + error);
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedCheckFile') });
      }
    }

    async function recheckFile(row) {
      row._checking = true;
      try {
        await axios.post(getCompressoApiUrl('v2', 'healthcheck/scan'), {
          file_path: row.abspath,
          library_id: row.library_id || selectedLibraryId.value,
          mode: scanMode.value,
        });
        await loadSummary();
        await loadStatuses();
      } catch (error) {
        log.error('Error re-checking file: ' + error);
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedRecheckFile') });
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
        const response = await axios.get(getCompressoApiUrl('v2', 'settings/read'));
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
        log.error('Error loading libraries: ' + error);
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedLoadLibraries') });
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
      scanModeOptions,
      statusFilterOptions,
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
