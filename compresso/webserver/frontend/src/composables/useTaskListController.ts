import { computed, nextTick, ref, shallowRef } from 'vue'

interface TaskRow {
  id: number
}

interface TaskPage<Row extends TaskRow> {
  rows: Row[]
  total: number
}

interface FetchPageOptions {
  start: number
  length: number
}

interface FetchTasksOptions {
  reset?: boolean
  silent?: boolean
  refreshTop?: boolean
}

interface TaskListControllerOptions<Row extends TaskRow, Filters extends object> {
  fetchPage: (options: FetchPageOptions) => Promise<TaskPage<Row>>
  buildFiltersPayload?: () => Filters
  onFetchError?: (error: unknown) => void
  pageSize?: number
}

/**
 * Shared state machine for the pending and completed task lists.
 *
 * The caller owns the API contract and row mapping through `fetchPage`; this
 * composable owns pagination, refresh merging, loading/error state, and the
 * explicit/all-filtered selection contract.
 */
export function useTaskListController<Row extends TaskRow, Filters extends object = Record<string, never>>(
  options: TaskListControllerOptions<Row, Filters>,
) {
  const { fetchPage, buildFiltersPayload = () => ({}) as Filters, onFetchError, pageSize = 50 } = options
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = shallowRef<unknown>(null)
  const rows = shallowRef<Row[]>([])
  const totalCount = ref(0)
  const offset = ref(0)

  const selectedIds = ref<number[]>([])
  const selectAllMatching = ref(false)
  const excludedIds = ref<number[]>([])

  const allLoaded = computed(() => totalCount.value === 0 || rows.value.length >= totalCount.value)

  const isRowSelected = (row: Row): boolean =>
    selectAllMatching.value ? !excludedIds.value.includes(row.id) : selectedIds.value.includes(row.id)

  const allPageSelected = computed(() => rows.value.length > 0 && rows.value.every((row) => isRowSelected(row)))

  const selectedCount = computed(() =>
    selectAllMatching.value ? Math.max(0, totalCount.value - excludedIds.value.length) : selectedIds.value.length,
  )

  const showSelectAllMatchingPrompt = computed(
    () => !selectAllMatching.value && allPageSelected.value && totalCount.value > rows.value.length,
  )

  const resetSelection = (): void => {
    selectedIds.value = []
    selectAllMatching.value = false
    excludedIds.value = []
  }

  const toggleRowSelection = (row: Row, value: boolean): void => {
    if (selectAllMatching.value) {
      if (value) {
        excludedIds.value = excludedIds.value.filter((id) => id !== row.id)
      } else if (!excludedIds.value.includes(row.id)) {
        excludedIds.value.push(row.id)
      }
      return
    }

    if (value && !selectedIds.value.includes(row.id)) {
      selectedIds.value.push(row.id)
    } else if (!value) {
      selectedIds.value = selectedIds.value.filter((id) => id !== row.id)
    }
  }

  const toggleSelectPage = (value: boolean): void => {
    if (!value) {
      resetSelection()
      return
    }
    for (const row of rows.value) {
      if (!selectedIds.value.includes(row.id)) {
        selectedIds.value.push(row.id)
      }
    }
  }

  const selectAllMatchingResults = (): void => {
    selectAllMatching.value = true
    selectedIds.value = []
    excludedIds.value = []
  }

  const getSelectionPayload = () => {
    if (selectAllMatching.value) {
      return {
        selection_mode: 'all_filtered',
        exclude_ids: [...excludedIds.value],
        ...buildFiltersPayload(),
      }
    }
    return {
      selection_mode: 'explicit',
      id_list: [...selectedIds.value],
    }
  }

  const mergePage = (pageRows: Row[], { reset, refreshTop }: Required<Pick<FetchTasksOptions, 'reset' | 'refreshTop'>>) => {
    if (refreshTop && rows.value.length > 0) {
      const refreshedIds = new Set(pageRows.map((row) => row.id))
      rows.value = [...pageRows, ...rows.value.filter((row) => !refreshedIds.has(row.id))]
    } else if (reset || refreshTop) {
      rows.value = pageRows
    } else {
      rows.value = [...rows.value, ...pageRows]
    }

    if (totalCount.value > 0 && rows.value.length > totalCount.value) {
      rows.value = rows.value.slice(0, totalCount.value)
    }
    offset.value = rows.value.length
  }

  const fetchTasks = async ({ reset = false, silent = false, refreshTop = false }: FetchTasksOptions = {}) => {
    if (reset) {
      offset.value = 0
      rows.value = []
    }

    if (reset && !silent) {
      loading.value = true
    } else {
      loadingMore.value = true
    }
    error.value = null

    try {
      const page = await fetchPage({
        start: refreshTop ? 0 : offset.value,
        length: pageSize,
      })
      totalCount.value = page.total
      mergePage(page.rows, { reset, refreshTop })
      return true
    } catch (caughtError) {
      error.value = caughtError
      onFetchError?.(caughtError)
      return false
    } finally {
      if (!silent) {
        loading.value = false
      }
      loadingMore.value = false
    }
  }

  const loadMore = (_index: number, done: (allLoaded: boolean) => void): void => {
    if (loading.value || loadingMore.value || allLoaded.value) {
      done(allLoaded.value)
      return
    }
    fetchTasks().finally(() => {
      nextTick(() => done(allLoaded.value))
    })
  }

  return {
    loading,
    loadingMore,
    error,
    rows,
    totalCount,
    offset,
    selectedIds,
    selectAllMatching,
    excludedIds,
    allLoaded,
    allPageSelected,
    selectedCount,
    showSelectAllMatchingPrompt,
    resetSelection,
    clearSelection: resetSelection,
    isRowSelected,
    toggleRowSelection,
    toggleSelectPage,
    selectAllMatchingResults,
    getSelectionPayload,
    fetchTasks,
    loadMore,
  }
}
