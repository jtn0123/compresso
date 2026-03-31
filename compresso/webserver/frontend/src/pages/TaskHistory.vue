<template>
  <q-page class="q-pa-md">

    <!-- Header -->
    <PageHeader
      :title="t('pages.taskHistory.title')"
      :subtitle="t('pages.taskHistory.subtitle')"
    >
      <template #actions>
        <q-btn
          flat
          icon="file_download"
          :label="t('pages.taskHistory.exportCsv')"
          :disable="tasks.length === 0"
          @click="exportCsv"
        />
        <q-btn-dropdown
          flat
          icon="view_column"
          :label="t('pages.taskHistory.columns')"
        >
          <q-list>
            <q-item v-for="col in allColumns" :key="col.name" dense>
              <q-item-section>
                <q-checkbox
                  :model-value="visibleColumnNames.includes(col.name)"
                  @update:model-value="toggleColumn(col.name)"
                  :label="col.label"
                  color="secondary"
                  dense
                />
              </q-item-section>
            </q-item>
          </q-list>
        </q-btn-dropdown>
        <q-btn flat icon="refresh" @click="fetchTasks({ reset: true })" />
      </template>
    </PageHeader>

    <!-- Search -->
    <div class="row q-col-gutter-sm q-mb-sm q-mt-md">
      <div class="col-12 col-sm-6 col-md-4">
        <q-input
          outlined
          dense
          debounce="300"
          v-model="searchValue"
          :placeholder="t('navigation.search')"
          color="secondary"
          clearable
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="row q-col-gutter-sm items-center q-mb-sm">
      <div class="col-auto">
        <q-btn-toggle
          v-model="statusFilter"
          toggle-color="secondary"
          :options="statusFilterOptions"
          dense
          no-caps
        />
      </div>
      <div class="col-auto">
        <q-input
          outlined
          dense
          v-model="afterDate"
          type="date"
          :label="t('pages.taskHistory.dateFrom')"
          color="secondary"
          clearable
          style="min-width: 160px"
        />
      </div>
      <div class="col-auto">
        <q-input
          outlined
          dense
          v-model="beforeDate"
          type="date"
          :label="t('pages.taskHistory.dateTo')"
          color="secondary"
          clearable
          style="min-width: 160px"
        />
      </div>
      <div class="col-auto">
        <q-select
          outlined
          dense
          v-model="codecFilter"
          :options="codecOptions"
          :label="t('pages.taskHistory.codec')"
          clearable
          emit-value
          map-options
          color="secondary"
          style="min-width: 140px"
        />
      </div>
      <div class="col-auto">
        <q-select
          outlined
          dense
          v-model="libraryFilter"
          :options="libraryOptions"
          :label="t('pages.taskHistory.library')"
          clearable
          emit-value
          map-options
          color="secondary"
          style="min-width: 160px"
        />
      </div>
      <q-space />
      <div class="col-auto">
        <q-select
          outlined
          dense
          v-model="sortBy"
          :options="sortOptions"
          :label="t('pages.taskHistory.sortBy')"
          emit-value
          map-options
          color="secondary"
          style="min-width: 160px"
        />
      </div>
      <div class="col-auto">
        <q-btn
          flat
          round
          :icon="descending ? 'arrow_downward' : 'arrow_upward'"
          @click="descending = !descending"
          :title="descending ? t('pages.taskHistory.sortDesc') : t('pages.taskHistory.sortAsc')"
        />
      </div>
    </div>

    <!-- Active filter chips -->
    <div v-if="activeFilterChips.length" class="row items-center q-gutter-sm q-mb-md">
      <q-chip
        v-for="chip in activeFilterChips"
        :key="chip.key"
        dense
        removable
        outline
        color="secondary"
        @remove="chip.remove"
      >
        {{ chip.label }}
      </q-chip>
    </div>

    <!-- Selection actions banner -->
    <q-slide-transition>
      <div v-if="selected.length > 0" class="row items-center q-gutter-sm q-mb-sm">
        <span class="text-body2">
          {{ t('pages.taskHistory.selectedCount', { count: selected.length }) }}
        </span>
        <q-btn
          flat
          dense
          color="secondary"
          icon="replay"
          :label="t('pages.taskHistory.reprocess')"
          @click="selectLibraryForReprocess"
        />
        <q-btn
          flat
          dense
          color="negative"
          icon="delete_outline"
          :label="t('pages.taskHistory.delete')"
          @click="deleteSelected"
        />
      </div>
    </q-slide-transition>

    <!-- Data table -->
    <q-table
      flat
      bordered
      :rows="tasks"
      :columns="visibleColumns"
      row-key="id"
      :loading="loading"
      selection="multiple"
      v-model:selected="selected"
      v-model:pagination="pagination"
      :rows-per-page-options="[25, 50, 100]"
      @request="onRequest"
      class="task-history-table"
    >
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-badge :color="props.row.task_success ? 'positive' : 'negative'">
            {{ props.row.task_success ? t('status.success') : t('status.failed') }}
          </q-badge>
        </q-td>
      </template>

      <template #body-cell-actions="props">
        <q-td :props="props" class="q-gutter-xs">
          <q-btn
            flat
            dense
            round
            icon="article"
            :title="t('pages.taskHistory.viewLog')"
            @click="openLog(props.row.id)"
          />
          <q-btn
            flat
            dense
            round
            icon="replay"
            :title="t('pages.taskHistory.reprocess')"
            @click="reprocessSingle(props.row)"
          />
          <q-btn
            flat
            dense
            round
            icon="delete_outline"
            color="negative"
            :title="t('pages.taskHistory.delete')"
            @click="deleteSingle(props.row)"
          />
        </q-td>
      </template>

      <template #no-data>
        <div class="full-width row flex-center text-accent q-gutter-sm q-pa-lg">
          <q-icon size="2em" name="sentiment_dissatisfied" />
          <span>{{ t('pages.taskHistory.noTasks') }}</span>
        </div>
      </template>
    </q-table>

    <!-- Log dialog -->
    <q-dialog v-model="logDialogOpen" backdrop-filter="blur(2px)">
      <q-card style="min-width: 60vw; max-width: 92vw;">
        <q-card-section class="bg-card-head row items-center">
          <div class="text-h6 text-primary">{{ t('pages.taskHistory.taskLog') }}</div>
          <q-space />
          <q-btn flat round icon="close" v-close-popup />
        </q-card-section>
        <q-separator />
        <q-card-section class="scroll" style="max-height: 70vh;">
          <q-inner-loading :showing="logLoading">
            <q-spinner-dots size="32px" color="secondary" />
          </q-inner-loading>
          <pre v-if="!logLoading" class="task-log-content">{{ logContent }}</pre>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Library select dialog for reprocess -->
    <q-dialog v-model="selectLibraryOpen" persistent>
      <q-card flat bordered style="min-width: 340px;">
        <q-card-section>
          <div class="text-h6 text-primary">{{ t('headers.selectLibrary') }}</div>
        </q-card-section>
        <q-card-section class="q-pt-none">
          <q-select
            outlined
            dense
            color="secondary"
            emit-value
            map-options
            v-model="selectedLibraryId"
            :options="reprocessLibraryOptions"
            :label="t('components.completedTasks.selectLibraryToAdd')"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat :label="t('navigation.cancel')" v-close-popup />
          <q-btn
            color="secondary"
            :label="t('navigation.submit')"
            @click="confirmReprocess"
            v-close-popup
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import dateTools from 'src/js/dateTools'
import PageHeader from 'components/ui/PageHeader.vue'

const { t } = useI18n()
const $q = useQuasar()

// --- State ---
const loading = ref(false)
const tasks = ref([])
const selected = ref([])
const totalCount = ref(0)

const searchValue = ref('')
const statusFilter = ref('all')
const afterDate = ref(null)
const beforeDate = ref(null)
const codecFilter = ref(null)
const libraryFilter = ref(null)
const sortBy = ref('finish_time')
const descending = ref(true)

const codecOptions = ref([])
const libraryOptions = ref([])

const logDialogOpen = ref(false)
const logLoading = ref(false)
const logContent = ref('')

const selectLibraryOpen = ref(false)
const selectedLibraryId = ref(null)
const reprocessLibraryOptions = ref([])
const pendingReprocessIds = ref([])

const COLUMN_STORAGE_KEY = 'compresso-task-history-columns'

const pagination = ref({
  sortBy: 'finish_time',
  descending: true,
  page: 1,
  rowsPerPage: 50,
  rowsNumber: 0,
})

// --- Columns ---
const allColumns = computed(() => [
  {
    name: 'task_label',
    label: t('pages.taskHistory.colFileName'),
    field: 'task_label',
    align: 'left',
    sortable: false,
  },
  {
    name: 'status',
    label: t('components.completedTasks.columns.status'),
    field: 'task_success',
    align: 'center',
    sortable: false,
  },
  {
    name: 'codec',
    label: t('pages.taskHistory.colCodec'),
    field: 'codec',
    align: 'left',
    sortable: false,
  },
  {
    name: 'size',
    label: t('pages.taskHistory.colSize'),
    field: 'size_display',
    align: 'right',
    sortable: false,
  },
  {
    name: 'duration',
    label: t('pages.taskHistory.colDuration'),
    field: 'duration_display',
    align: 'right',
    sortable: false,
  },
  {
    name: 'finish_time',
    label: t('components.completedTasks.columns.completed'),
    field: 'finish_time_display',
    align: 'left',
    sortable: false,
  },
  {
    name: 'actions',
    label: '',
    field: 'id',
    align: 'center',
    sortable: false,
  },
])

function loadVisibleColumns() {
  try {
    const stored = localStorage.getItem(COLUMN_STORAGE_KEY)
    if (stored) return JSON.parse(stored)
  } catch { /* ignore */ }
  return allColumns.value.map(c => c.name)
}

const visibleColumnNames = ref(loadVisibleColumns())

const visibleColumns = computed(() =>
  allColumns.value.filter(c => visibleColumnNames.value.includes(c.name))
)

function toggleColumn(name) {
  const idx = visibleColumnNames.value.indexOf(name)
  if (idx >= 0) {
    // Don't allow removing the last column
    if (visibleColumnNames.value.length <= 1) return
    visibleColumnNames.value.splice(idx, 1)
  } else {
    visibleColumnNames.value.push(name)
  }
  try {
    localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(visibleColumnNames.value))
  } catch { /* ignore */ }
}

// --- Filter options ---
const statusFilterOptions = computed(() => [
  { label: t('status.all'), value: 'all' },
  { label: t('status.success'), value: 'success' },
  { label: t('status.failed'), value: 'failed' },
])

const sortOptions = computed(() => [
  { label: t('components.completedTasks.columns.completed'), value: 'finish_time' },
  { label: t('components.completedTasks.columns.name'), value: 'task_label' },
  { label: t('components.completedTasks.columns.status'), value: 'task_success' },
])

const activeFilterChips = computed(() => {
  const chips = []
  if (statusFilter.value !== 'all') {
    const label = statusFilterOptions.value.find(o => o.value === statusFilter.value)?.label || statusFilter.value
    chips.push({
      key: 'status',
      label: t('components.completedTasks.filterStatus', { status: label }),
      remove: () => { statusFilter.value = 'all' },
    })
  }
  if (afterDate.value) {
    chips.push({
      key: 'after',
      label: t('components.completedTasks.filterSince', { date: afterDate.value }),
      remove: () => { afterDate.value = null },
    })
  }
  if (beforeDate.value) {
    chips.push({
      key: 'before',
      label: t('components.completedTasks.filterBefore', { date: beforeDate.value }),
      remove: () => { beforeDate.value = null },
    })
  }
  if (codecFilter.value) {
    chips.push({
      key: 'codec',
      label: t('pages.taskHistory.colCodec') + ': ' + codecFilter.value,
      remove: () => { codecFilter.value = null },
    })
  }
  if (libraryFilter.value) {
    const lib = libraryOptions.value.find(o => o.value === libraryFilter.value)
    chips.push({
      key: 'library',
      label: t('pages.taskHistory.library') + ': ' + (lib?.label || libraryFilter.value),
      remove: () => { libraryFilter.value = null },
    })
  }
  return chips
})

// --- Fetch tasks ---
function buildPayload(page, rowsPerPage) {
  const start = (page - 1) * rowsPerPage
  return {
    start,
    length: rowsPerPage,
    search_value: searchValue.value || '',
    status: statusFilter.value,
    after: afterDate.value || null,
    before: beforeDate.value || null,
    order_by: sortBy.value,
    order_direction: descending.value ? 'desc' : 'asc',
  }
}

async function fetchTasks({ reset = false } = {}) {
  if (reset) {
    pagination.value.page = 1
    selected.value = []
  }
  loading.value = true
  try {
    const data = buildPayload(pagination.value.page, pagination.value.rowsPerPage)
    const response = await axios.post(getCompressoApiUrl('v2', 'history/tasks'), data)
    totalCount.value = response.data.recordsFiltered
    pagination.value.rowsNumber = totalCount.value

    tasks.value = (response.data.results || []).map(r => ({
      id: r.id,
      task_label: r.task_label,
      task_success: r.task_success,
      codec: r.codec || '',
      size_display: r.file_size ? formatBytes(r.file_size) : '',
      duration_display: r.processing_duration ? dateTools.printSecondsAsDuration(r.processing_duration) : '',
      finish_time_display: r.finish_time ? dateTools.printDateTimeString(r.finish_time) : '',
      finish_time: r.finish_time,
    }))
  } catch {
    $q.notify({
      color: 'negative',
      position: 'top',
      message: t('components.completedTasks.errorFetchingList'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }],
    })
  } finally {
    loading.value = false
  }
}

function onRequest(props) {
  const { page, rowsPerPage, sortBy: col, descending: desc } = props.pagination
  pagination.value.page = page
  pagination.value.rowsPerPage = rowsPerPage
  if (col) {
    sortBy.value = col
    descending.value = desc
  }
  fetchTasks()
}

// --- Library + codec bootstrap ---
async function fetchLibraries() {
  try {
    const response = await axios.get(getCompressoApiUrl('v2', 'settings/libraries'))
    libraryOptions.value = (response.data.libraries || []).map(lib => ({
      label: lib.name,
      value: lib.id,
    }))
  } catch { /* ignore */ }
}

async function fetchCodecs() {
  try {
    // Try to populate from first page of history data
    const response = await axios.post(getCompressoApiUrl('v2', 'history/tasks'), {
      start: 0,
      length: 200,
      status: 'all',
      search_value: '',
      order_by: 'finish_time',
      order_direction: 'desc',
    })
    const codecs = new Set()
    ;(response.data.results || []).forEach(r => {
      if (r.codec) codecs.add(r.codec)
    })
    codecOptions.value = Array.from(codecs).sort().map(c => ({ label: c, value: c }))
  } catch { /* ignore */ }
}

// --- Log viewer ---
async function openLog(taskId) {
  logDialogOpen.value = true
  logLoading.value = true
  logContent.value = ''
  try {
    const response = await axios.post(getCompressoApiUrl('v2', 'history/task/log'), { task_id: taskId })
    logContent.value = response.data.log || t('pages.taskHistory.noLogAvailable')
  } catch {
    logContent.value = t('components.completedTasks.errorGettingDetails')
  } finally {
    logLoading.value = false
  }
}

// --- Reprocess ---
function reprocessSingle(row) {
  pendingReprocessIds.value = [row.id]
  openLibrarySelect()
}

function selectLibraryForReprocess() {
  pendingReprocessIds.value = selected.value.map(s => s.id)
  openLibrarySelect()
}

async function openLibrarySelect() {
  try {
    const response = await axios.get(getCompressoApiUrl('v2', 'settings/libraries'))
    const libs = (response.data.libraries || []).map(lib => ({
      label: lib.name,
      value: lib.id,
    }))
    reprocessLibraryOptions.value = libs

    if (libs.length === 1) {
      selectedLibraryId.value = libs[0].value
      confirmReprocess()
    } else {
      selectedLibraryId.value = libs[0]?.value || null
      selectLibraryOpen.value = true
    }
  } catch {
    $q.notify({
      color: 'negative',
      position: 'top',
      message: t('notifications.failedToFetchLibraryList'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }],
    })
  }
}

async function confirmReprocess() {
  selectLibraryOpen.value = false
  try {
    await axios.post(getCompressoApiUrl('v2', 'history/reprocess'), {
      selection_mode: 'explicit',
      id_list: pendingReprocessIds.value,
      library_id: selectedLibraryId.value,
    })
    selected.value = []
    fetchTasks({ reset: true })
  } catch {
    $q.notify({
      color: 'negative',
      position: 'top',
      message: t('components.completedTasks.errorAddSelected'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }],
    })
  }
}

// --- Delete ---
function deleteSingle(row) {
  $q.dialog({
    title: t('headers.confirm'),
    message: t('pages.taskHistory.confirmDelete'),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    try {
      await axios({
        method: 'delete',
        url: getCompressoApiUrl('v2', 'history/tasks'),
        data: { selection_mode: 'explicit', id_list: [row.id] },
      })
      fetchTasks({ reset: true })
    } catch {
      $q.notify({
        color: 'negative',
        position: 'top',
        message: t('components.completedTasks.errorDeleteSelected'),
        icon: 'report_problem',
        actions: [{ icon: 'close', color: 'white' }],
      })
    }
  })
}

function deleteSelected() {
  if (selected.value.length === 0) return
  $q.dialog({
    title: t('headers.confirm'),
    message: t('pages.taskHistory.confirmDeleteSelected', { count: selected.value.length }),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    try {
      await axios({
        method: 'delete',
        url: getCompressoApiUrl('v2', 'history/tasks'),
        data: {
          selection_mode: 'explicit',
          id_list: selected.value.map(s => s.id),
        },
      })
      selected.value = []
      fetchTasks({ reset: true })
    } catch {
      $q.notify({
        color: 'negative',
        position: 'top',
        message: t('components.completedTasks.errorDeleteSelected'),
        icon: 'report_problem',
        actions: [{ icon: 'close', color: 'white' }],
      })
    }
  })
}

// --- CSV export ---
function exportCsv() {
  const cols = visibleColumns.value.filter(c => c.name !== 'actions')
  const headers = cols.map(c => c.label).join(',')
  const rows = tasks.value.map(task =>
    cols.map(c => {
      let val = task[c.field] ?? ''
      if (c.name === 'status') {
        val = task.task_success ? 'Success' : 'Failed'
      }
      return `"${String(val).replace(/"/g, '""')}"`
    }).join(',')
  )
  const csv = [headers, ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `compresso-history-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// --- Utilities ---
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// --- Watchers ---
watch([searchValue, statusFilter, afterDate, beforeDate, codecFilter, libraryFilter], () => {
  fetchTasks({ reset: true })
})

watch([sortBy, descending], () => {
  fetchTasks({ reset: true })
})

// --- Lifecycle ---
onMounted(() => {
  fetchTasks({ reset: true })
  fetchLibraries()
  fetchCodecs()
})
</script>

<style scoped>
.task-history-table {
  max-height: calc(100vh - 340px);
}

.task-log-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: monospace;
  font-size: 0.82rem;
  line-height: 1.5;
  margin: 0;
}
</style>
