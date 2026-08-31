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
                :disable="scanPhase === 'cancelling'"
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
                flat
                round
                dense
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
                flat
                round
                dense
                icon="add"
                size="sm"
                :aria-label="$t('a11y.addLibrary')"
                :disable="workerCount >= 16"
                @click="changeWorkerCount(1)"
              />
            </div>
          </div>

          <!-- Scan Progress Panel -->
          <div v-if="showScanProgress" class="q-mt-md" data-testid="scan-progress">
            <q-banner dense rounded class="q-mb-sm" :class="`bg-${scanPhaseColor} text-white`" data-testid="scan-phase">
              <div class="row items-center no-wrap">
                <q-icon :name="scanPhaseIcon" size="sm" class="q-mr-sm" />
                <div>
                  <div class="text-weight-medium">{{ scanPhaseLabel }}</div>
                  <div v-if="scanPhase === 'discovering'" class="text-caption">
                    {{
                      $t('pages.healthCheck.discoveryCounts', {
                        discovered: scanProgress.discovered || 0,
                        checked: scanProgress.checked || 0,
                      })
                    }}
                  </div>
                  <div v-if="scanPhase === 'failed' && scanProgress.error" class="text-caption">
                    {{ scanProgress.error }}
                  </div>
                </div>
              </div>
            </q-banner>
            <div class="row items-center q-mb-sm">
              <div class="col">
                <q-linear-progress :value="scanProgressPercent" color="primary" size="20px" rounded>
                  <div class="absolute-full flex flex-center">
                    <span class="text-white text-caption" style="text-shadow: 0 0 3px rgba(0, 0, 0, 0.5)">
                      {{ scanProgress.checked }} / {{ scanProgress.total }} ({{
                        Math.round(scanProgressPercent * 100)
                      }}%)
                    </span>
                  </div>
                </q-linear-progress>
              </div>
            </div>
            <div class="row q-col-gutter-md q-mb-sm">
              <div class="col-auto">
                <span class="text-caption">
                  {{ $t('pages.healthCheck.speedLabel') }} {{ scanProgress.files_per_second || 0 }}
                  {{ $t('pages.healthCheck.filesPerSec') }}
                </span>
              </div>
              <div v-if="scanProgress.discovery_complete" class="col-auto">
                <span class="text-caption">
                  {{ $t('pages.healthCheck.etaLabel') }} {{ formatEta(scanProgress.eta_seconds) }}
                </span>
              </div>
              <div v-else-if="scanPhase === 'discovering'" class="col-auto">
                <span class="text-caption">{{ $t('pages.healthCheck.etaAfterDiscovery') }}</span>
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
            <q-banner
              :class="
                singleFileResult.status === 'healthy'
                  ? 'bg-positive text-white'
                  : singleFileResult.status === 'warning'
                    ? 'bg-warning text-white'
                    : 'bg-negative text-white'
              "
            >
              <strong>{{ singleFileResult.abspath }}</strong
              >: {{ singleFileResult.status }}
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
                <template #prepend>
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
              <template #body-cell-status="props">
                <q-td :props="props">
                  <q-badge :color="getStatusColor(props.row.status)">
                    {{ props.row.status }}
                  </q-badge>
                </q-td>
              </template>
              <template #body-cell-actions="props">
                <q-td :props="props">
                  <q-btn
                    flat
                    round
                    dense
                    icon="refresh"
                    size="sm"
                    :aria-label="$t('a11y.refresh')"
                    @click="recheckFile(props.row)"
                    :loading="props.row._checking"
                  />
                  <q-btn
                    flat
                    round
                    dense
                    icon="info"
                    size="sm"
                    :aria-label="$t('a11y.libraryDetails')"
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

<script lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { QTableColumn } from 'quasar'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { displayBasename } from 'src/js/pathUtils'
import { createLogger } from 'src/composables/useLogger'
import FileInfoDialog from 'components/fileinfo/FileInfoDialog.vue'
import AdmonitionBanner from 'components/ui/AdmonitionBanner.vue'
import PageHeader from 'components/ui/PageHeader.vue'
import type { ApiSchema } from 'src/types/contracts'

type ScanMode = 'quick' | 'thorough'
interface ScanWorker {
  status: string
  current_file: string
}
interface HealthProgressView extends Omit<ApiSchema<'HealthCheckProgress'>, 'workers'> {
  workers: Record<string, ScanWorker>
}
interface HealthStatusRow {
  abspath: string
  status: string
  check_mode?: string
  error_detail?: string | null
  last_checked?: string
  error_count?: number
  library_id?: number
  _checking: boolean
}
interface LibraryOption {
  label: string
  value: number
}
interface LibraryWire {
  id: number
  name?: string
}
interface TableRequest {
  pagination: { page: number; rowsPerPage: number; sortBy: string; descending: boolean }
}
interface FileInfoController {
  probeByPath(path: string): void
}

const normalizeProgress = (progress?: ApiSchema<'HealthCheckProgress'>): HealthProgressView => {
  const workers: Record<string, ScanWorker> = {}
  for (const [id, value] of Object.entries(progress?.workers ?? {})) {
    if (typeof value !== 'object' || value === null) continue
    const worker = value as Record<string, unknown>
    workers[id] = {
      status: typeof worker.status === 'string' ? worker.status : 'idle',
      current_file: typeof worker.current_file === 'string' ? worker.current_file : '',
    }
  }
  return { ...progress, workers }
}

const isHealthStatusRow = (value: unknown): value is Omit<HealthStatusRow, '_checking'> => {
  if (typeof value !== 'object' || value === null) return false
  const row = value as Record<string, unknown>
  return typeof row.abspath === 'string' && typeof row.status === 'string'
}

const isLibraryWire = (value: unknown): value is LibraryWire => {
  if (typeof value !== 'object' || value === null) return false
  const library = value as Record<string, unknown>
  return typeof library.id === 'number' && (library.name === undefined || typeof library.name === 'string')
}

export default {
  name: 'HealthCheck',
  components: { FileInfoDialog, AdmonitionBanner, PageHeader },
  setup() {
    const $q = useQuasar()
    const { t } = useI18n()
    const log = createLogger('HealthCheck')
    const loadingSummary = ref(true)
    const summary = ref<ApiSchema<'HealthCheckSummaryResponse'>>({
      success: true,
      healthy: 0,
      warning: 0,
      corrupted: 0,
      unchecked: 0,
      checking: 0,
      total: 0,
    })
    const scanning = ref(false)
    const scanProgress = ref<HealthProgressView>({
      phase: 'idle',
      total: 0,
      discovered: 0,
      discovery_complete: false,
      checked: 0,
      cancelled: false,
      error: null,
      workers: {},
      files_per_second: 0,
      eta_seconds: 0,
    })
    const workerCount = ref(1)
    const scanProgressPercent = ref(0)
    const selectedLibraryId = ref(1)
    const scanMode = ref<ScanMode>('quick')
    const libraryOptions = ref<LibraryOption[]>([{ label: 'Default Library', value: 1 }])
    const singleFilePath = ref('')
    const singleFileResult = ref<ApiSchema<'HealthCheckScanResponse'> | null>(null)
    const searchValue = ref('')
    const statusFilter = ref<string | null>(null)
    const statusResults = ref<HealthStatusRow[]>([])
    const loadingStatuses = ref(false)
    const fileInfoDialogRef = ref<FileInfoController | null>(null)
    let pollTimer: ReturnType<typeof setTimeout> | null = null

    const pagination = ref({
      page: 1,
      rowsPerPage: 20,
      rowsNumber: 0,
      sortBy: 'last_checked',
      descending: true,
    })

    const statusColumns = computed<QTableColumn[]>(() => [
      {
        name: 'abspath',
        label: t('pages.healthCheck.columnFilePath'),
        field: 'abspath',
        align: 'left',
        sortable: true,
      },
      { name: 'status', label: t('pages.healthCheck.columnStatus'), field: 'status', align: 'center', sortable: true },
      { name: 'check_mode', label: t('pages.healthCheck.columnMode'), field: 'check_mode', align: 'center' },
      { name: 'error_detail', label: t('pages.healthCheck.columnErrorDetail'), field: 'error_detail', align: 'left' },
      {
        name: 'last_checked',
        label: t('pages.healthCheck.columnLastChecked'),
        field: 'last_checked',
        align: 'left',
        sortable: true,
      },
      { name: 'error_count', label: t('pages.healthCheck.columnErrors'), field: 'error_count', align: 'center' },
      { name: 'actions', label: t('pages.healthCheck.columnActions'), field: 'actions', align: 'center' },
    ])

    const scanModeOptions = computed(() => [
      { label: t('pages.healthCheck.modeQuick'), value: 'quick' },
      { label: t('pages.healthCheck.modeThorough'), value: 'thorough' },
    ])

    const statusFilterOptions = computed(() => [
      { label: t('pages.healthCheck.filterAll'), value: null },
      { label: t('pages.healthCheck.filterHealthy'), value: 'healthy' },
      { label: t('pages.healthCheck.filterWarning'), value: 'warning' },
      { label: t('pages.healthCheck.filterCorrupted'), value: 'corrupted' },
      { label: t('pages.healthCheck.filterUnchecked'), value: 'unchecked' },
    ])

    const scanPhase = computed(() => scanProgress.value.phase || (scanning.value ? 'checking' : 'idle'))
    const showScanProgress = computed(
      () => scanning.value || ['complete', 'cancelled', 'failed'].includes(scanPhase.value),
    )
    const scanPhaseLabel = computed(() => {
      const labels: Record<string, string> = {
        discovering: 'pages.healthCheck.phaseDiscovering',
        checking: 'pages.healthCheck.phaseChecking',
        cancelling: 'pages.healthCheck.phaseCancelling',
        complete: 'pages.healthCheck.phaseComplete',
        cancelled: 'pages.healthCheck.phaseCancelled',
        failed: 'pages.healthCheck.phaseFailed',
      }
      return t(labels[scanPhase.value] || 'pages.healthCheck.phaseIdle')
    })
    const scanPhaseColor = computed(() => {
      if (scanPhase.value === 'failed') return 'negative'
      if (scanPhase.value === 'cancelled' || scanPhase.value === 'cancelling') return 'warning'
      if (scanPhase.value === 'complete') return 'positive'
      return 'info'
    })
    const scanPhaseIcon = computed(() => {
      if (scanPhase.value === 'failed') return 'error'
      if (scanPhase.value === 'cancelled') return 'cancel'
      if (scanPhase.value === 'complete') return 'check_circle'
      if (scanPhase.value === 'cancelling') return 'pending'
      if (scanPhase.value === 'discovering') return 'travel_explore'
      return 'fact_check'
    })

    function getStatusColor(status: string): string {
      if (status === 'healthy') return 'positive'
      if (status === 'warning') return 'warning'
      if (status === 'corrupted') return 'negative'
      if (status === 'checking') return 'info'
      return 'grey'
    }

    async function loadSummary() {
      try {
        const url = selectedLibraryId.value
          ? getCompressoApiUrl('v2', 'healthcheck/summary') + '?library_id=' + selectedLibraryId.value
          : getCompressoApiUrl('v2', 'healthcheck/summary')
        const response = await axios.get<ApiSchema<'HealthCheckSummaryResponse'>>(url)
        if (response.data) {
          summary.value = response.data
          scanning.value = response.data.scanning || false
          if (response.data.scan_progress) {
            scanProgress.value = normalizeProgress(response.data.scan_progress)
            const total = response.data.scan_progress.total || 0
            const checked = response.data.scan_progress.checked || 0
            scanProgressPercent.value = total > 0 ? checked / total : 0
          }
        }
      } catch (error) {
        log.error('Error loading health summary: ' + error)
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedLoadSummary') })
      } finally {
        loadingSummary.value = false
      }
    }

    async function loadWorkerInfo() {
      try {
        const response = await axios.get<ApiSchema<'HealthCheckWorkersResponse'>>(
          getCompressoApiUrl('v2', 'healthcheck/workers'),
        )
        if (response.data) {
          workerCount.value = response.data.worker_count || 1
          if (response.data.scan_progress) {
            scanProgress.value = normalizeProgress(response.data.scan_progress)
            const total = response.data.scan_progress.total || 0
            const checked = response.data.scan_progress.checked || 0
            scanProgressPercent.value = total > 0 ? checked / total : 0
          }
        }
      } catch (error) {
        log.error('Error loading worker info: ' + error)
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedLoadWorkerInfo') })
      }
    }

    async function changeWorkerCount(delta: number): Promise<void> {
      const newCount = workerCount.value + delta
      if (newCount < 1 || newCount > 16) return
      try {
        const response = await axios.post(getCompressoApiUrl('v2', 'healthcheck/workers'), {
          worker_count: newCount,
        })
        if (response.data) {
          workerCount.value = response.data.worker_count || newCount
        }
      } catch (error) {
        log.error('Error setting worker count: ' + error)
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedUpdateWorkerCount') })
      }
    }

    function formatEta(seconds: number | undefined): string {
      if (!seconds || seconds <= 0) return '--'
      const h = Math.floor(seconds / 3600)
      const m = Math.floor((seconds % 3600) / 60)
      const s = seconds % 60
      if (h > 0) return h + 'h ' + m + 'm'
      if (m > 0) return m + 'm ' + s + 's'
      return s + 's'
    }

    function truncateFilename(filepath: string): string {
      if (!filepath) return ''
      const name = displayBasename(filepath)
      return name.length > 50 ? name.substring(0, 47) + '...' : name
    }

    async function loadStatuses() {
      loadingStatuses.value = true
      try {
        const start = (pagination.value.page - 1) * pagination.value.rowsPerPage
        const response = await axios.post<ApiSchema<'HealthCheckStatusResponse'>>(
          getCompressoApiUrl('v2', 'healthcheck/status'),
          {
            start: start,
            length: pagination.value.rowsPerPage,
            search_value: searchValue.value,
            library_id: selectedLibraryId.value,
            status_filter: statusFilter.value,
            order_by: pagination.value.sortBy || 'last_checked',
            order_direction: pagination.value.descending ? 'desc' : 'asc',
          },
        )
        if (response.data) {
          statusResults.value = (response.data.results || [])
            .filter(isHealthStatusRow)
            .map((row) => ({ ...row, _checking: false }))
          pagination.value.rowsNumber = response.data.recordsFiltered || 0
        }
      } catch (error) {
        log.error('Error loading health statuses: ' + error)
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedLoadStatuses') })
      } finally {
        loadingStatuses.value = false
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
          const response = await axios.post<ApiSchema<'HealthCheckLibraryScanResponse'>>(
            getCompressoApiUrl('v2', 'healthcheck/scan-library'),
            {
              library_id: selectedLibraryId.value,
              mode: scanMode.value,
            },
          )
          if (response.data) {
            scanning.value = response.data.started ?? false
            if (response.data.started) {
              startPolling()
              $q.notify({ type: 'positive', message: t('pages.healthCheck.scanStarted') })
            } else {
              $q.notify({
                type: 'warning',
                message: response.data.message || t('pages.healthCheck.scanAlreadyInProgress'),
              })
            }
          }
        } catch (error) {
          log.error('Error starting library scan: ' + error)
          $q.notify({ type: 'negative', message: t('pages.healthCheck.failedStartScan') })
        }
      })
    }

    async function cancelScan() {
      try {
        await axios.post(getCompressoApiUrl('v2', 'healthcheck/cancel-scan'))
        scanProgress.value = { ...scanProgress.value, phase: 'cancelling' }
        $q.notify({ type: 'info', message: t('pages.healthCheck.scanCancelRequested') })
      } catch (error) {
        log.error('Error cancelling scan: ' + error)
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedCancelScan') })
      }
    }

    async function checkSingleFile() {
      singleFileResult.value = null
      try {
        const response = await axios.post<ApiSchema<'HealthCheckScanResponse'>>(
          getCompressoApiUrl('v2', 'healthcheck/scan'),
          {
            file_path: singleFilePath.value,
            library_id: selectedLibraryId.value,
            mode: scanMode.value,
          },
        )
        if (response.data) {
          singleFileResult.value = response.data
          await loadSummary()
          await loadStatuses()
        }
      } catch (error) {
        log.error('Error checking file: ' + error)
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedCheckFile') })
      }
    }

    async function recheckFile(row: HealthStatusRow): Promise<void> {
      row._checking = true
      try {
        await axios.post(getCompressoApiUrl('v2', 'healthcheck/scan'), {
          file_path: row.abspath,
          library_id: row.library_id || selectedLibraryId.value,
          mode: scanMode.value,
        })
        await loadSummary()
        await loadStatuses()
      } catch (error) {
        log.error('Error re-checking file: ' + error)
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedRecheckFile') })
      } finally {
        row._checking = false
      }
    }

    function showFileInfo(filePath: string): void {
      fileInfoDialogRef.value?.probeByPath(filePath)
    }

    function onTableRequest(props: TableRequest): void {
      const { page, rowsPerPage, sortBy, descending } = props.pagination
      pagination.value.page = page
      pagination.value.rowsPerPage = rowsPerPage
      pagination.value.sortBy = sortBy
      pagination.value.descending = descending
      loadStatuses()
    }

    let pollCount = 0
    function getPollInterval() {
      if (pollCount > 20) return 15000
      if (pollCount > 10) return 5000
      return 2000
    }

    function startPolling() {
      stopPolling()
      pollCount = 0
      function doPoll() {
        pollTimer = setTimeout(async () => {
          pollCount++
          await Promise.all([loadSummary(), loadWorkerInfo()])
          if (!scanning.value) {
            stopPolling()
            await loadStatuses()
          } else {
            doPoll()
          }
        }, getPollInterval())
      }
      doPoll()
    }

    function stopPolling() {
      if (pollTimer) {
        clearTimeout(pollTimer)
        pollTimer = null
      }
    }

    async function loadLibraries() {
      try {
        const response = await axios.get(getCompressoApiUrl('v2', 'settings/read'))
        if (response.data && response.data.settings) {
          const rawLibraries: unknown = response.data.settings.libraries
          const libs = Array.isArray(rawLibraries) ? rawLibraries.filter(isLibraryWire) : []
          if (libs.length > 0) {
            libraryOptions.value = libs.map((lib) => ({
              label: lib.name || `Library ${lib.id}`,
              value: lib.id,
            }))
            const firstLibrary = libs[0]
            if (firstLibrary) selectedLibraryId.value = firstLibrary.id
          }
        }
      } catch (error) {
        log.error('Error loading libraries: ' + error)
        $q.notify({ type: 'negative', message: t('pages.healthCheck.failedLoadLibraries') })
      }
    }

    watch(
      () => selectedLibraryId.value,
      () => {
        pagination.value.page = 1
        loadStatuses()
        loadSummary()
      },
    )

    onMounted(async () => {
      await loadLibraries()
      await Promise.all([loadSummary(), loadStatuses()])
      if (scanning.value) startPolling()
    })

    onBeforeUnmount(() => {
      stopPolling()
    })

    return {
      summary,
      scanning,
      scanProgress,
      scanProgressPercent,
      scanPhase,
      showScanProgress,
      scanPhaseLabel,
      scanPhaseColor,
      scanPhaseIcon,
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
    }
  },
}
</script>
