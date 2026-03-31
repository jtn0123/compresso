import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: vi.fn((version, endpoint) => `http://localhost/compresso/api/${version}/${endpoint}`),
  showEventToast: vi.fn(),
}))

vi.mock('src/composables/useLogger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

vi.mock('src/js/dateTools', () => ({
  default: {
    printSecondsAsDuration: vi.fn((s) => `${s}s`),
    printDateTimeString: vi.fn((ts) => `2025-01-01 00:00:00`),
  },
}))

const dialogOnOk = vi.fn()
const mockDialog = vi.fn(() => ({ onOk: dialogOnOk }))
const mockNotify = vi.fn()

vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({
    notify: mockNotify,
    dialog: mockDialog,
    dark: { isActive: false },
    screen: {
      gt: { xs: true, sm: true },
      lt: { sm: false, md: false },
    },
  }),
  Notify: { create: vi.fn() },
  Dialog: {},
  LocalStorage: { getItem: vi.fn(), setItem: vi.fn() },
  SessionStorage: { getItem: vi.fn(), setItem: vi.fn() },
}))

import axios from 'axios'
import { shallowMountWithQuasar } from 'src/test-utils'
import TaskHistory from '../TaskHistory.vue'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_TASKS = [
  {
    id: 101,
    task_label: 'movie1.mkv',
    task_success: true,
    codec: 'hevc',
    file_size: 1048576,
    processing_duration: 120,
    finish_time: 1700000000,
  },
  {
    id: 102,
    task_label: 'movie2.mp4',
    task_success: false,
    codec: 'h264',
    file_size: 2097152,
    processing_duration: 300,
    finish_time: 1700001000,
  },
  {
    id: 103,
    task_label: 'show1.mkv',
    task_success: true,
    codec: 'av1',
    file_size: 524288,
    processing_duration: 60,
    finish_time: 1700002000,
  },
]

const MOCK_LIBRARIES = [
  { id: 'lib-1', name: 'Movies' },
  { id: 'lib-2', name: 'TV Shows' },
]

function mockFetchSuccess(tasks = MOCK_TASKS) {
  axios.post.mockImplementation((url) => {
    if (url.includes('history/tasks')) {
      return Promise.resolve({
        data: {
          results: tasks,
          recordsFiltered: tasks.length,
        },
      })
    }
    if (url.includes('history/task/log')) {
      return Promise.resolve({ data: { log: 'Processing started\nProcessing complete' } })
    }
    if (url.includes('history/reprocess')) {
      return Promise.resolve({ data: { success: true } })
    }
    return Promise.resolve({ data: {} })
  })
  axios.get.mockImplementation((url) => {
    if (url.includes('settings/libraries')) {
      return Promise.resolve({
        data: { libraries: MOCK_LIBRARIES },
      })
    }
    return Promise.resolve({ data: {} })
  })
  axios.delete = vi.fn().mockResolvedValue({ data: { success: true } })
}

function mockFetchEmpty() {
  axios.post.mockImplementation((url) => {
    if (url.includes('history/tasks')) {
      return Promise.resolve({
        data: { results: [], recordsFiltered: 0 },
      })
    }
    return Promise.resolve({ data: {} })
  })
  axios.get.mockImplementation(() =>
    Promise.resolve({ data: { libraries: [] } }),
  )
}

async function mountTaskHistory(mockFn = mockFetchSuccess) {
  mockFn()
  const wrapper = shallowMountWithQuasar(TaskHistory, {
    global: {
      stubs: {
        'q-btn-toggle': { template: '<div class="q-btn-toggle" />', props: ['modelValue', 'options'] },
        'q-chip': { template: '<span class="q-chip"><slot /></span>', props: ['removable'] },
        'q-slide-transition': { template: '<div><slot /></div>' },
        'q-space': { template: '<div />' },
        'q-toggle': { template: '<input type="checkbox" class="q-toggle" />' },
        'q-inner-loading': { template: '<div class="q-inner-loading"><slot /></div>' },
        'q-spinner-dots': { template: '<span class="q-spinner-dots" />' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TaskHistory.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Stub localStorage
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // 1. Renders page header
  describe('rendering', () => {
    it('renders the PageHeader component', async () => {
      const wrapper = await mountTaskHistory()
      expect(wrapper.findComponent({ name: 'PageHeader' }).exists()).toBe(true)
    })
  })

  // 2. Shows search input
  describe('search input', () => {
    it('searchValue starts as empty string', async () => {
      const wrapper = await mountTaskHistory()
      expect(wrapper.vm.searchValue).toBe('')
    })

    it('searchValue can be updated', async () => {
      const wrapper = await mountTaskHistory()
      wrapper.vm.searchValue = 'movie'
      await wrapper.vm.$nextTick()
      expect(wrapper.vm.searchValue).toBe('movie')
    })
  })

  // 3. Status filter buttons render (All/Success/Failed)
  describe('status filter', () => {
    it('statusFilter defaults to all', async () => {
      const wrapper = await mountTaskHistory()
      expect(wrapper.vm.statusFilter).toBe('all')
    })

    it('statusFilterOptions contains all, success, and failed', async () => {
      const wrapper = await mountTaskHistory()
      const values = wrapper.vm.statusFilterOptions.map((o) => o.value)
      expect(values).toEqual(['all', 'success', 'failed'])
    })
  })

  // 4. Fetches tasks on mount
  describe('fetch on mount', () => {
    it('calls history/tasks endpoint on mount', async () => {
      await mountTaskHistory()
      const taskCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('history/tasks'),
      )
      // At least 1 call for fetchTasks, plus 1 for fetchCodecs
      expect(taskCalls.length).toBeGreaterThanOrEqual(1)
    })

    it('populates tasks array after successful fetch', async () => {
      const wrapper = await mountTaskHistory()
      expect(wrapper.vm.tasks).toHaveLength(3)
      expect(wrapper.vm.tasks[0].task_label).toBe('movie1.mkv')
    })

    it('sets loading to false after fetch resolves', async () => {
      const wrapper = await mountTaskHistory()
      expect(wrapper.vm.loading).toBe(false)
    })
  })

  // 5. Renders table rows with task data
  describe('task data', () => {
    it('maps task fields correctly', async () => {
      const wrapper = await mountTaskHistory()
      const firstTask = wrapper.vm.tasks[0]

      expect(firstTask.id).toBe(101)
      expect(firstTask.task_label).toBe('movie1.mkv')
      expect(firstTask.task_success).toBe(true)
      expect(firstTask.codec).toBe('hevc')
    })

    it('formats size correctly', async () => {
      const wrapper = await mountTaskHistory()
      // 1048576 bytes = 1 MB
      expect(wrapper.vm.tasks[0].size_display).toBe('1 MB')
    })
  })

  // 6. CSV export generates correct content
  describe('csv export', () => {
    it('exportCsv creates a download link', async () => {
      const wrapper = await mountTaskHistory()

      const createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue({
        href: '',
        download: '',
        click: vi.fn(),
      })
      const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
      const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

      wrapper.vm.exportCsv()

      expect(createObjectURLSpy).toHaveBeenCalled()
      expect(revokeObjectURLSpy).toHaveBeenCalled()

      createElementSpy.mockRestore()
      createObjectURLSpy.mockRestore()
      revokeObjectURLSpy.mockRestore()
    })
  })

  // 7. Column visibility toggle works
  describe('column visibility', () => {
    it('toggleColumn removes a column from visibleColumnNames', async () => {
      const wrapper = await mountTaskHistory()
      const initialCount = wrapper.vm.visibleColumnNames.length

      wrapper.vm.toggleColumn('codec')
      expect(wrapper.vm.visibleColumnNames).not.toContain('codec')
      expect(wrapper.vm.visibleColumnNames.length).toBe(initialCount - 1)
    })

    it('toggleColumn adds a column back', async () => {
      const wrapper = await mountTaskHistory()

      wrapper.vm.toggleColumn('codec')
      expect(wrapper.vm.visibleColumnNames).not.toContain('codec')

      wrapper.vm.toggleColumn('codec')
      expect(wrapper.vm.visibleColumnNames).toContain('codec')
    })

    it('does not allow removing the last column', async () => {
      const wrapper = await mountTaskHistory()
      // Remove all but one column
      const columns = [...wrapper.vm.visibleColumnNames]
      for (let i = 0; i < columns.length - 1; i++) {
        wrapper.vm.toggleColumn(columns[i])
      }
      expect(wrapper.vm.visibleColumnNames.length).toBe(1)

      // Try to remove the last one
      wrapper.vm.toggleColumn(wrapper.vm.visibleColumnNames[0])
      expect(wrapper.vm.visibleColumnNames.length).toBe(1)
    })
  })

  // 8. Filter chips appear when filters active
  describe('filter chips', () => {
    it('shows no filter chips when all filters are default', async () => {
      const wrapper = await mountTaskHistory()
      expect(wrapper.vm.activeFilterChips).toHaveLength(0)
    })

    it('shows a status chip when status filter is set', async () => {
      const wrapper = await mountTaskHistory()
      wrapper.vm.statusFilter = 'success'
      await wrapper.vm.$nextTick()

      const chips = wrapper.vm.activeFilterChips
      expect(chips.some((c) => c.key === 'status')).toBe(true)
    })

    it('shows a date chip when afterDate is set', async () => {
      const wrapper = await mountTaskHistory()
      wrapper.vm.afterDate = '2025-01-01'
      await wrapper.vm.$nextTick()

      const chips = wrapper.vm.activeFilterChips
      expect(chips.some((c) => c.key === 'after')).toBe(true)
    })

    it('shows a codec chip when codecFilter is set', async () => {
      const wrapper = await mountTaskHistory()
      wrapper.vm.codecFilter = 'hevc'
      await wrapper.vm.$nextTick()

      const chips = wrapper.vm.activeFilterChips
      expect(chips.some((c) => c.key === 'codec')).toBe(true)
    })
  })

  // 9. Removing a filter chip clears that filter
  describe('removing filter chips', () => {
    it('removing status chip resets statusFilter to all', async () => {
      const wrapper = await mountTaskHistory()
      wrapper.vm.statusFilter = 'failed'
      await wrapper.vm.$nextTick()

      const statusChip = wrapper.vm.activeFilterChips.find((c) => c.key === 'status')
      statusChip.remove()
      await wrapper.vm.$nextTick()

      expect(wrapper.vm.statusFilter).toBe('all')
    })

    it('removing date chip clears afterDate', async () => {
      const wrapper = await mountTaskHistory()
      wrapper.vm.afterDate = '2025-01-01'
      await wrapper.vm.$nextTick()

      const dateChip = wrapper.vm.activeFilterChips.find((c) => c.key === 'after')
      dateChip.remove()
      await wrapper.vm.$nextTick()

      expect(wrapper.vm.afterDate).toBeNull()
    })
  })

  // 10. Reprocess action calls correct API
  describe('reprocess action', () => {
    it('reprocessSingle sets pending IDs and triggers library select', async () => {
      const wrapper = await mountTaskHistory()
      const row = wrapper.vm.tasks[0]

      wrapper.vm.reprocessSingle(row)
      await flushPromises()

      expect(wrapper.vm.pendingReprocessIds).toEqual([101])
    })

    it('confirmReprocess calls the reprocess endpoint', async () => {
      const wrapper = await mountTaskHistory()
      wrapper.vm.pendingReprocessIds = [101]
      wrapper.vm.selectedLibraryId = 'lib-1'

      vi.clearAllMocks()
      mockFetchSuccess()

      await wrapper.vm.confirmReprocess()
      await flushPromises()

      const reprocessCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('history/reprocess'),
      )
      expect(reprocessCalls.length).toBe(1)
      expect(reprocessCalls[0][1]).toEqual({
        selection_mode: 'explicit',
        id_list: [101],
        library_id: 'lib-1',
      })
    })
  })

  // 11. Delete action shows confirmation
  describe('delete action', () => {
    it('deleteSingle calls $q.dialog', async () => {
      const wrapper = await mountTaskHistory()
      const row = wrapper.vm.tasks[0]

      wrapper.vm.deleteSingle(row)

      expect(mockDialog).toHaveBeenCalled()
    })

    it('deleteSelected does nothing when selection is empty', async () => {
      const wrapper = await mountTaskHistory()
      wrapper.vm.selected = []
      wrapper.vm.deleteSelected()

      expect(mockDialog).not.toHaveBeenCalled()
    })
  })

  // 12. View log opens dialog
  describe('view log', () => {
    it('openLog sets logDialogOpen and fetches log content', async () => {
      const wrapper = await mountTaskHistory()
      expect(wrapper.vm.logDialogOpen).toBe(false)

      vi.clearAllMocks()
      mockFetchSuccess()

      await wrapper.vm.openLog(101)
      await flushPromises()

      expect(wrapper.vm.logDialogOpen).toBe(true)
      expect(wrapper.vm.logContent).toBe('Processing started\nProcessing complete')
      expect(wrapper.vm.logLoading).toBe(false)
    })

    it('openLog handles fetch failure gracefully', async () => {
      const wrapper = await mountTaskHistory()
      axios.post.mockRejectedValueOnce(new Error('Network error'))

      await wrapper.vm.openLog(999)
      await flushPromises()

      expect(wrapper.vm.logDialogOpen).toBe(true)
      expect(wrapper.vm.logLoading).toBe(false)
      // Falls back to an error message (i18n key)
      expect(wrapper.vm.logContent).toBeTruthy()
    })
  })

  // 13. Pagination works (page change triggers fetch)
  describe('pagination', () => {
    it('onRequest updates pagination and triggers a fetch', async () => {
      const wrapper = await mountTaskHistory()
      vi.clearAllMocks()
      mockFetchSuccess()

      // Use the same sortBy to avoid watcher reset
      wrapper.vm.onRequest({
        pagination: {
          page: 2,
          rowsPerPage: 25,
          sortBy: 'finish_time',
          descending: true,
        },
      })
      await flushPromises()

      expect(wrapper.vm.pagination.page).toBe(2)
      expect(wrapper.vm.pagination.rowsPerPage).toBe(25)

      const taskCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('history/tasks'),
      )
      expect(taskCalls.length).toBeGreaterThanOrEqual(1)
    })

    it('onRequest updates sortBy when a different column is specified', async () => {
      const wrapper = await mountTaskHistory()
      vi.clearAllMocks()
      mockFetchSuccess()

      wrapper.vm.onRequest({
        pagination: {
          page: 1,
          rowsPerPage: 50,
          sortBy: 'task_label',
          descending: false,
        },
      })
      await flushPromises()

      expect(wrapper.vm.sortBy).toBe('task_label')
      expect(wrapper.vm.descending).toBe(false)
    })

    it('pagination.rowsNumber is updated from API response', async () => {
      const wrapper = await mountTaskHistory()
      expect(wrapper.vm.pagination.rowsNumber).toBe(3)
    })
  })

  // Empty state
  describe('empty state', () => {
    it('tasks array is empty when API returns no results', async () => {
      const wrapper = await mountTaskHistory(mockFetchEmpty)
      expect(wrapper.vm.tasks).toEqual([])
    })
  })

  // Error handling
  describe('error handling', () => {
    it('handles fetch failure gracefully and sets loading to false', async () => {
      axios.post.mockRejectedValue(new Error('Network error'))
      axios.get.mockRejectedValue(new Error('Network error'))

      const wrapper = shallowMountWithQuasar(TaskHistory, {
        global: {
          stubs: {
            'q-btn-toggle': { template: '<div />' },
            'q-chip': { template: '<span />' },
            'q-slide-transition': { template: '<div><slot /></div>' },
            'q-space': { template: '<div />' },
            'q-toggle': { template: '<input type="checkbox" />' },
            'q-inner-loading': { template: '<div><slot /></div>' },
            'q-spinner-dots': { template: '<span />' },
          },
        },
      })
      await flushPromises()

      expect(wrapper.vm.loading).toBe(false)
      expect(wrapper.vm.tasks).toEqual([])
    })
  })
})
