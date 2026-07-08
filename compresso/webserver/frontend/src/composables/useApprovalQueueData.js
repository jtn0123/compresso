import { computed, ref } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'

const EMPTY_SUMMARY = {
  total_count: 0,
  total_source_size: 0,
  total_staged_size: 0,
  total_space_saved: 0,
  average_savings_percent: 0,
  largest_savings_file: '',
  largest_savings_bytes: 0,
  average_vmaf: null,
  codec_options: [],
}

function fileName(abspath) {
  if (!abspath) return ''
  return abspath.split('/').pop()
}

function formatSize(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let size = Math.abs(bytes)
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return size.toFixed(1) + ' ' + units[i]
}

function summaryFromTasks(rows) {
  const withVmaf = rows.filter((t) => t.vmaf_score != null)
  const validSavings = rows.filter((t) => t.source_size > 0)
  let largest = rows[0] || null
  for (const row of rows) {
    if (Math.abs(row.size_delta || 0) > Math.abs(largest?.size_delta || 0)) {
      largest = row
    }
  }

  return {
    ...EMPTY_SUMMARY,
    total_count: rows.length,
    total_source_size: rows.reduce((sum, t) => sum + (t.source_size || 0), 0),
    total_staged_size: rows.reduce((sum, t) => sum + (t.staged_size || 0), 0),
    total_space_saved: rows.reduce((sum, t) => {
      const delta = t.size_delta || 0
      return delta < 0 ? sum + Math.abs(delta) : sum
    }, 0),
    average_savings_percent:
      validSavings.length === 0
        ? 0
        : validSavings.reduce((sum, t) => sum + ((t.source_size - t.staged_size) / t.source_size) * 100, 0) /
          validSavings.length,
    largest_savings_file: largest?.abspath || '',
    largest_savings_bytes: Math.abs(largest?.size_delta || 0),
    average_vmaf: withVmaf.length === 0 ? null : withVmaf.reduce((sum, t) => sum + t.vmaf_score, 0) / withVmaf.length,
    codec_options: Array.from(
      new Set(rows.flatMap((t) => [t.source_codec, t.staged_codec]).filter((codec) => Boolean(codec))),
    ).sort(),
  }
}

function normalizeSummary(data) {
  return {
    ...EMPTY_SUMMARY,
    ...data,
    codec_options: Array.isArray(data?.codec_options) ? data.codec_options : [],
  }
}

export function useApprovalQueueData({ notify, t } = {}) {
  const tasks = ref([])
  const loading = ref(false)
  const newItemCount = ref(0)
  const searchValue = ref('')
  const filterCodec = ref(null)
  const filterQualityMin = ref(0)
  const summary = ref({ ...EMPTY_SUMMARY })
  let lastKnownIds = new Set()

  const pagination = ref({
    page: 1,
    rowsPerPage: 25,
    rowsNumber: 0,
    sortBy: 'finish_time',
    descending: true,
  })

  function buildFilterPayload() {
    return {
      search_value: searchValue.value || '',
      codec: filterCodec.value || '',
      quality_min: Number(filterQualityMin.value) || 0,
    }
  }

  function buildBulkFilterPayload() {
    return buildFilterPayload()
  }

  function buildTaskPayload(pg) {
    const start = (pg.page - 1) * pg.rowsPerPage
    return {
      start,
      length: pg.rowsPerPage,
      ...buildFilterPayload(),
      order_by: pg.sortBy || 'finish_time',
      order_direction: pg.descending ? 'desc' : 'asc',
      include_library: false,
    }
  }

  async function fetchSummary() {
    try {
      const res = await axios.post(getCompressoApiUrl('v2', 'approval/summary'), buildFilterPayload())
      summary.value = normalizeSummary(res.data)
    } catch {
      summary.value = summaryFromTasks(tasks.value)
    }
  }

  async function fetchTasks(props, selectedIds = []) {
    loading.value = true
    const pg = props && props.pagination ? props.pagination : pagination.value

    try {
      const res = await axios.post(getCompressoApiUrl('v2', 'approval/tasks'), buildTaskPayload(pg))
      const data = res.data
      const newTasks = data.results || []
      const newCount = data.recordsFiltered || 0

      const newIds = new Set(newTasks.map((task) => task.id))
      if (lastKnownIds.size > 0) {
        let addedCount = 0
        for (const id of newIds) {
          if (!lastKnownIds.has(id)) addedCount++
        }
        if (addedCount > 0 && tasks.value.length > 0) {
          newItemCount.value += addedCount
        }
      }

      tasks.value = newTasks
      lastKnownIds = newIds
      pagination.value.rowsNumber = newCount
      pagination.value.page = pg.page
      pagination.value.rowsPerPage = pg.rowsPerPage
      pagination.value.sortBy = pg.sortBy
      pagination.value.descending = pg.descending

      const selectedIdSet = new Set(selectedIds)
      return newTasks.filter((task) => selectedIdSet.has(task.id))
    } catch {
      if (notify) {
        notify({
          type: 'negative',
          message: t ? t('pages.approvalQueue.failedToFetchTasks') : 'Failed to fetch approval tasks',
          timeout: 3000,
          position: 'top',
        })
      }
      return null
    } finally {
      loading.value = false
    }
  }

  const totalSpaceSaved = computed(() => summary.value.total_space_saved || 0)
  const avgSavingsPercent = computed(() => Number(summary.value.average_savings_percent || 0).toFixed(1))
  const largestFileName = computed(() => fileName(summary.value.largest_savings_file) || '-')
  const largestFileSavings = computed(() => {
    const bytes = summary.value.largest_savings_bytes || 0
    return bytes ? `${formatSize(bytes)} ${t ? t('pages.approvalQueue.saved') : 'saved'}` : ''
  })
  const avgVmafScore = computed(() => summary.value.average_vmaf)
  const codecOptions = computed(() =>
    summary.value.codec_options.map((codec) => ({
      label: codec,
      value: codec,
    })),
  )
  const hasActiveFilters = computed(() => filterCodec.value !== null || filterQualityMin.value > 0)

  return {
    tasks,
    loading,
    pagination,
    newItemCount,
    searchValue,
    filterCodec,
    filterQualityMin,
    summary,
    totalSpaceSaved,
    avgSavingsPercent,
    largestFileName,
    largestFileSavings,
    avgVmafScore,
    codecOptions,
    hasActiveFilters,
    buildBulkFilterPayload,
    fetchSummary,
    fetchTasks,
  }
}
