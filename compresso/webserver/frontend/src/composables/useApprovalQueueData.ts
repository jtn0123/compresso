import { computed, ref } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { displayBasename } from 'src/js/pathUtils'
import type { ApiSchema } from 'src/types/contracts'
import type { Notify, Translate } from 'src/types/ui'

export interface ApprovalTask extends ApiSchema<'ApprovalTaskItem'> {
  id: number
  abspath: string
  source_size: number
  staged_size: number
  size_delta: number
  source_codec: string
  staged_codec: string
  vmaf_score: number | null
}

interface ApprovalSummaryState {
  total_count: number
  total_source_size: number
  total_staged_size: number
  total_space_saved: number
  average_savings_percent: number
  largest_savings_file: string
  largest_savings_bytes: number
  average_vmaf: number | null
  codec_options: string[]
}

export interface ApprovalPagination {
  page: number
  rowsPerPage: number
  rowsNumber: number
  sortBy: NonNullable<ApiSchema<'RequestApprovalTasks'>['order_by']>
  descending: boolean
}

export interface FetchTaskProps {
  pagination?: ApprovalPagination
}

interface ApprovalQueueDataOptions {
  notify?: Notify
  t?: Translate
}

const EMPTY_SUMMARY: ApprovalSummaryState = {
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

export function fileName(abspath: string): string {
  return displayBasename(abspath)
}

export function formatSize(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let size = Math.abs(bytes)
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return size.toFixed(1) + ' ' + (units[i] ?? 'B')
}

function summaryFromTasks(rows: ApprovalTask[]): ApprovalSummaryState {
  const withVmaf = rows.filter((t) => t.vmaf_score != null)
  const validSavings = rows.filter((t) => t.source_size > 0 && t.staged_size > 0)
  let largest: ApprovalTask | null = null
  for (const row of rows) {
    const delta = row.size_delta || 0
    if (delta >= 0) continue
    if (Math.abs(delta) > Math.abs(largest?.size_delta || 0)) {
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
    average_vmaf:
      withVmaf.length === 0 ? null : withVmaf.reduce((sum, t) => sum + (t.vmaf_score ?? 0), 0) / withVmaf.length,
    codec_options: Array.from(
      new Set(rows.flatMap((t) => [t.source_codec, t.staged_codec]).filter((codec): codec is string => Boolean(codec))),
    ).sort(),
  }
}

function normalizeSummary(data: ApiSchema<'ApprovalSummaryResponse'>): ApprovalSummaryState {
  return {
    ...EMPTY_SUMMARY,
    ...data,
    codec_options: Array.isArray(data.codec_options) ? data.codec_options : [],
  }
}

export function useApprovalQueueData({ notify, t }: ApprovalQueueDataOptions = {}) {
  const tasks = ref<ApprovalTask[]>([])
  const loading = ref(false)
  const newItemCount = ref(0)
  const searchValue = ref('')
  const filterCodec = ref<string | null>(null)
  const filterQualityMin = ref(0)
  const summary = ref<ApprovalSummaryState>({ ...EMPTY_SUMMARY })
  const summaryError = ref('')
  const summaryIsPartial = ref(false)
  let fetchSequence = 0
  let lastTaskPayloadKey = ''
  let lastKnownIds = new Set<number>()

  const pagination = ref<ApprovalPagination>({
    page: 1,
    rowsPerPage: 25,
    rowsNumber: 0,
    sortBy: 'finish_time',
    descending: true,
  })

  function buildFilterPayload(): Pick<ApiSchema<'RequestApprovalTasks'>, 'search_value' | 'codec' | 'quality_min'> {
    return {
      search_value: searchValue.value || '',
      codec: filterCodec.value || '',
      quality_min: Number(filterQualityMin.value) || 0,
    }
  }

  function buildBulkFilterPayload() {
    return buildFilterPayload()
  }

  function buildTaskPayload(pg: ApprovalPagination): ApiSchema<'RequestApprovalTasks'> {
    const start = (pg.page - 1) * pg.rowsPerPage
    return {
      start,
      length: pg.rowsPerPage,
      library_ids: [],
      ...buildFilterPayload(),
      order_by: pg.sortBy || 'finish_time',
      order_direction: pg.descending ? 'desc' : 'asc',
      include_library: false,
    }
  }

  async function fetchSummary(): Promise<void> {
    try {
      const res = await axios.post<ApiSchema<'ApprovalSummaryResponse'>>(
        getCompressoApiUrl('v2', 'approval/summary'),
        buildFilterPayload(),
      )
      summary.value = normalizeSummary(res.data)
      summaryError.value = ''
      summaryIsPartial.value = false
    } catch {
      summary.value = summaryFromTasks(tasks.value)
      summaryError.value = t
        ? t('pages.approvalQueue.summaryPartial')
        : 'Summary temporarily unavailable; showing this page only.'
      summaryIsPartial.value = true
    }
  }

  async function fetchTasks(props?: FetchTaskProps, selectedIds: number[] = []): Promise<ApprovalTask[] | null> {
    const sequence = ++fetchSequence
    loading.value = true
    const pg = props && props.pagination ? props.pagination : pagination.value
    const payload = buildTaskPayload(pg)
    const payloadKey = JSON.stringify(payload)
    const isSameViewRefresh = payloadKey === lastTaskPayloadKey

    try {
      const res = await axios.post<ApiSchema<'ApprovalTasksResponse'>>(getCompressoApiUrl('v2', 'approval/tasks'), payload)
      if (sequence !== fetchSequence) return null

      const data = res.data
      const newTasks = (data.results ?? []) as ApprovalTask[]
      const newCount = data.recordsFiltered ?? 0

      const newIds = new Set(newTasks.map((task) => task.id))
      if (isSameViewRefresh && lastKnownIds.size > 0) {
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
      lastTaskPayloadKey = payloadKey
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
      if (sequence === fetchSequence) loading.value = false
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
    summaryError,
    summaryIsPartial,
    totalSpaceSaved,
    avgSavingsPercent,
    largestFileName,
    largestFileSavings,
    avgVmafScore,
    codecOptions,
    hasActiveFilters,
    fileName,
    formatSize,
    buildBulkFilterPayload,
    fetchSummary,
    fetchTasks,
  }
}
