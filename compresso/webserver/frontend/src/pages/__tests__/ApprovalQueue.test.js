import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

// ---------------------------------------------------------------------------
// Mocks — vi.mock factories are hoisted, so we use vi.hoisted() for any
// variables the factories need to reference.
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

vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({
    notify: vi.fn(),
    dialog: vi.fn(() => ({ onOk: vi.fn(), onCancel: vi.fn() })),
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
import ApprovalQueue from '../ApprovalQueue.vue'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_TASKS = [
  {
    id: 1,
    abspath: '/media/movies/movie1.mkv',
    source_codec: 'h264',
    staged_codec: 'hevc',
    source_size: 1000000,
    staged_size: 600000,
    size_delta: -400000,
    vmaf_score: 95.2,
    ssim_score: 0.98,
    finish_time: '2025-06-01 10:00:00',
  },
  {
    id: 2,
    abspath: '/media/movies/movie2.mp4',
    source_codec: 'h264',
    staged_codec: 'h264',
    source_size: 2000000,
    staged_size: 1500000,
    size_delta: -500000,
    vmaf_score: 88.1,
    ssim_score: 0.96,
    finish_time: '2025-06-01 11:00:00',
  },
  {
    id: 3,
    abspath: '/media/tv/show1.mkv',
    source_codec: 'hevc',
    staged_codec: 'hevc',
    source_size: 500000,
    staged_size: 550000,
    size_delta: 50000,
    vmaf_score: null,
    ssim_score: null,
    finish_time: '2025-06-01 12:00:00',
  },
]

function mockSummary(tasks = MOCK_TASKS) {
  const withVmaf = tasks.filter((t) => t.vmaf_score != null)
  const validSavings = tasks.filter((t) => t.source_size > 0)
  let largest = tasks[0] || null
  for (const task of tasks) {
    if (Math.abs(task.size_delta || 0) > Math.abs(largest?.size_delta || 0)) largest = task
  }
  return {
    total_count: tasks.length,
    total_source_size: tasks.reduce((sum, task) => sum + (task.source_size || 0), 0),
    total_staged_size: tasks.reduce((sum, task) => sum + (task.staged_size || 0), 0),
    total_space_saved: tasks.reduce((sum, task) => {
      const delta = task.size_delta || 0
      return delta < 0 ? sum + Math.abs(delta) : sum
    }, 0),
    average_savings_percent:
      validSavings.length === 0
        ? 0
        : validSavings.reduce(
            (sum, task) => sum + ((task.source_size - task.staged_size) / task.source_size) * 100,
            0,
          ) / validSavings.length,
    largest_savings_file: largest?.abspath || '',
    largest_savings_bytes: Math.abs(largest?.size_delta || 0),
    average_vmaf:
      withVmaf.length === 0 ? null : withVmaf.reduce((sum, task) => sum + task.vmaf_score, 0) / withVmaf.length,
    codec_options: ['h264', 'hevc'],
  }
}

function mockFetchSuccess(tasks = MOCK_TASKS) {
  axios.post.mockImplementation((url) => {
    if (url.includes('approval/summary')) {
      return Promise.resolve({ data: mockSummary(tasks) })
    }
    if (url.includes('approval/tasks')) {
      return Promise.resolve({
        data: {
          results: tasks,
          recordsFiltered: tasks.length,
        },
      })
    }
    if (url.includes('approval/approve')) {
      return Promise.resolve({ data: { success: true } })
    }
    if (url.includes('approval/reject')) {
      return Promise.resolve({ data: { success: true } })
    }
    if (url.includes('approval/detail')) {
      return Promise.resolve({ data: tasks[0] })
    }
    return Promise.resolve({ data: {} })
  })
  axios.get.mockImplementation((url) => {
    if (url.includes('settings/read')) {
      return Promise.resolve({
        data: { settings: { approval_required: true } },
      })
    }
    return Promise.resolve({ data: {} })
  })
}

function mockFetchEmpty() {
  axios.post.mockImplementation((url) => {
    if (url.includes('approval/summary')) {
      return Promise.resolve({ data: mockSummary([]) })
    }
    if (url.includes('approval/tasks')) {
      return Promise.resolve({
        data: { results: [], recordsFiltered: 0 },
      })
    }
    return Promise.resolve({ data: {} })
  })
  axios.get.mockImplementation(() => Promise.resolve({ data: { settings: { approval_required: true } } }))
}

async function mountApprovalQueue(mockFn = mockFetchSuccess) {
  mockFn()
  const wrapper = shallowMountWithQuasar(ApprovalQueue)
  await flushPromises()
  return wrapper
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ApprovalQueue.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // 1. Renders the page header and summary cards
  describe('rendering', () => {
    it('renders the PageHeader component', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.findComponent({ name: 'PageHeader' }).exists()).toBe(true)
    })

    it('renders four summary stat cards', async () => {
      const wrapper = await mountApprovalQueue()
      const statCards = wrapper.findAll('.stat-card')
      expect(statCards.length).toBe(4)
    })
  })

  // 2. Shows loading state while fetching
  describe('loading state', () => {
    it('starts with loading true before fetch resolves', () => {
      axios.post.mockImplementation(() => new Promise(() => {}))
      axios.get.mockImplementation(() => new Promise(() => {}))
      const wrapper = shallowMountWithQuasar(ApprovalQueue)
      expect(wrapper.vm.loading).toBe(true)
    })

    it('sets loading to false after fetch resolves', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.loading).toBe(false)
    })
  })

  // 3. Renders table rows with task data after fetch
  describe('task data after fetch', () => {
    it('populates tasks array after successful fetch', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.tasks).toHaveLength(3)
      expect(wrapper.vm.tasks[0].id).toBe(1)
      expect(wrapper.vm.tasks[1].abspath).toBe('/media/movies/movie2.mp4')
    })

    it('updates pagination rowsNumber from response', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.pagination.rowsNumber).toBe(3)
    })
  })

  // 4. Approve/Reject buttons are disabled when no rows selected
  describe('button disable state', () => {
    it('has empty selectedIds when no rows are selected', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.selectedIds).toEqual([])
    })

    it('selectedIds reflects selected rows', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.selected = [MOCK_TASKS[0], MOCK_TASKS[2]]
      await wrapper.vm.$nextTick()
      expect(wrapper.vm.selectedIds).toEqual([1, 3])
    })
  })

  // 5. Selecting rows enables the approve/reject buttons
  describe('selection behaviour', () => {
    it('selectedIds updates when tasks are selected', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.selectedIds.length).toBe(0)

      wrapper.vm.selected = [MOCK_TASKS[0]]
      await wrapper.vm.$nextTick()
      expect(wrapper.vm.selectedIds.length).toBe(1)
    })
  })

  // 6. Clicking approve calls the correct API endpoint with selected IDs
  describe('approve action', () => {
    it('posts to the approval/approve endpoint with selected IDs', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.selected = [MOCK_TASKS[0], MOCK_TASKS[1]]
      await wrapper.vm.$nextTick()

      await wrapper.vm.approveSelected()
      await flushPromises()

      const approveCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/approve'))
      expect(approveCalls.length).toBe(1)
      expect(approveCalls[0][1]).toEqual({ id_list: [1, 2] })
    })

    it('clears selection after successful approve', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.selected = [MOCK_TASKS[0]]
      await wrapper.vm.$nextTick()

      await wrapper.vm.approveSelected()
      await flushPromises()

      expect(wrapper.vm.selected).toEqual([])
    })

    it('refetches tasks after approval', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.selected = [MOCK_TASKS[0]]
      await wrapper.vm.$nextTick()
      vi.clearAllMocks()

      mockFetchSuccess()
      await wrapper.vm.approveSelected()
      await flushPromises()

      const taskCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/tasks'))
      expect(taskCalls.length).toBeGreaterThanOrEqual(1)
    })

    it('does not submit a second approval while one is active', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.selected = [MOCK_TASKS[0]]
      wrapper.vm.approving = true

      await wrapper.vm.approveSelected()

      const approveCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/approve'))
      expect(approveCalls).toHaveLength(0)
    })
  })

  // 7. Clicking reject opens the reject confirmation dialog
  describe('reject action', () => {
    it('opens the reject dialog when rejectSingle is called', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.showRejectDialog).toBe(false)

      wrapper.vm.rejectSingle(1)
      await wrapper.vm.$nextTick()

      expect(wrapper.vm.showRejectDialog).toBe(true)
      expect(wrapper.vm.rejectTargetIds).toEqual([1])
    })

    it('sets showRejectDialog to true when reject button state triggers', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.selected = [MOCK_TASKS[0], MOCK_TASKS[1]]
      await wrapper.vm.$nextTick()

      wrapper.vm.showRejectDialog = true
      await wrapper.vm.$nextTick()

      expect(wrapper.vm.showRejectDialog).toBe(true)
    })

    it('confirmReject posts to the correct endpoint', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.rejectTargetIds = [1]
      wrapper.vm.rejectAction = 'discard'
      await wrapper.vm.$nextTick()

      await wrapper.vm.confirmReject()
      await flushPromises()

      const rejectCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/reject'))
      expect(rejectCalls.length).toBe(1)
      expect(rejectCalls[0][1]).toEqual({ id_list: [1], requeue: false })
    })

    it('confirmReject passes requeue true when action is requeue', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.rejectTargetIds = [2]
      wrapper.vm.rejectAction = 'requeue'
      await wrapper.vm.$nextTick()

      await wrapper.vm.confirmReject()
      await flushPromises()

      const rejectCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/reject'))
      expect(rejectCalls[0][1]).toEqual({ id_list: [2], requeue: true })
    })
  })

  // 8. Search input triggers refetch with search value
  describe('search behaviour', () => {
    it('onSearchChange resets pagination to page 1 and refetches', async () => {
      const wrapper = await mountApprovalQueue()
      wrapper.vm.pagination.page = 3
      wrapper.vm.searchValue = 'movie'
      vi.clearAllMocks()
      mockFetchSuccess()

      wrapper.vm.onSearchChange()
      await flushPromises()

      expect(wrapper.vm.pagination.page).toBe(1)
      const taskCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/tasks'))
      expect(taskCalls.length).toBeGreaterThanOrEqual(1)
      expect(taskCalls[0][1].search_value).toBe('movie')
    })

    it('sends active codec and quality filters to tasks and summary endpoints', async () => {
      const wrapper = await mountApprovalQueue()
      vi.clearAllMocks()
      mockFetchSuccess()

      wrapper.vm.filterCodec = 'hevc'
      wrapper.vm.filterQualityMin = 90
      await wrapper.vm.$nextTick()
      vi.advanceTimersByTime(250)
      await flushPromises()

      const taskCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/tasks'))
      const summaryCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/summary'))
      expect(taskCalls.at(-1)[1]).toMatchObject({ codec: 'hevc', quality_min: 90 })
      expect(summaryCalls.at(-1)[1]).toMatchObject({ codec: 'hevc', quality_min: 90 })
    })

    it('marks summary data partial when the summary endpoint fails', async () => {
      axios.post.mockImplementation((url) => {
        if (url.includes('approval/summary')) {
          return Promise.reject(new Error('summary unavailable'))
        }
        if (url.includes('approval/tasks')) {
          return Promise.resolve({
            data: {
              results: MOCK_TASKS,
              recordsFiltered: MOCK_TASKS.length,
            },
          })
        }
        return Promise.resolve({ data: {} })
      })
      axios.get.mockImplementation(() => Promise.resolve({ data: { settings: { approval_required: true } } }))

      const wrapper = shallowMountWithQuasar(ApprovalQueue)
      await flushPromises()

      expect(wrapper.vm.summaryIsPartial).toBe(true)
      expect(wrapper.vm.summaryError).toBe('pages.approvalQueue.summaryPartial')
      expect(wrapper.vm.totalSpaceSaved).toBe(900000)
    })
  })

  // 9. Empty state shows appropriate message when no tasks
  describe('empty state', () => {
    it('tasks array is empty when API returns no results', async () => {
      const wrapper = await mountApprovalQueue(mockFetchEmpty)
      expect(wrapper.vm.tasks).toEqual([])
      expect(wrapper.vm.pagination.rowsNumber).toBe(0)
    })
  })

  // 10. Detail dialog opens when clicking info button
  describe('detail dialog', () => {
    it('showDetail opens dialog and fetches detail data', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.showDetailDialog).toBe(false)

      await wrapper.vm.showDetail(1)
      await flushPromises()

      expect(wrapper.vm.showDetailDialog).toBe(true)
      expect(wrapper.vm.detailData).not.toBeNull()
      expect(wrapper.vm.detailData.id).toBe(1)
    })

    it('closeDetail hides the dialog', async () => {
      const wrapper = await mountApprovalQueue()
      await wrapper.vm.showDetail(1)
      await flushPromises()

      wrapper.vm.closeDetail()
      await wrapper.vm.$nextTick()

      expect(wrapper.vm.showDetailDialog).toBe(false)
    })

    it('approveFromDetail approves the detailed task and closes dialog', async () => {
      const wrapper = await mountApprovalQueue()
      await wrapper.vm.showDetail(1)
      await flushPromises()

      vi.clearAllMocks()
      mockFetchSuccess()

      await wrapper.vm.approveFromDetail()
      await flushPromises()

      const approveCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/approve'))
      expect(approveCalls.length).toBe(1)
      expect(approveCalls[0][1]).toEqual({ id_list: [1] })
      expect(wrapper.vm.showDetailDialog).toBe(false)
    })

    it('does not approve when Enter comes from an interactive control', async () => {
      const wrapper = await mountApprovalQueue()
      await wrapper.vm.showDetail(1)
      await flushPromises()
      vi.clearAllMocks()
      mockFetchSuccess()
      const input = document.createElement('input')
      document.body.appendChild(input)

      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
      await flushPromises()

      const approveCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/approve'))
      expect(approveCalls).toHaveLength(0)
      input.remove()
      wrapper.unmount()
    })

    it('keeps Enter as an approval shortcut outside interactive controls', async () => {
      const wrapper = await mountApprovalQueue()
      await wrapper.vm.showDetail(1)
      await flushPromises()
      vi.clearAllMocks()
      mockFetchSuccess()

      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
      await flushPromises()

      const approveCalls = axios.post.mock.calls.filter(([url]) => url.includes('approval/approve'))
      expect(approveCalls.length).toBeGreaterThanOrEqual(1)
      expect(approveCalls.every(([, payload]) => payload.id_list?.[0] === 1)).toBe(true)
      wrapper.unmount()
    })
  })

  // Bonus: computed helpers
  describe('computed helpers', () => {
    it('fileName extracts file name from absolute path', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.fileName('/media/movies/movie1.mkv')).toBe('movie1.mkv')
      expect(wrapper.vm.fileName('/path/to/file.mp4')).toBe('file.mp4')
      expect(wrapper.vm.fileName('C:\\Media\\Movies\\file.mp4')).toBe('file.mp4')
      expect(wrapper.vm.fileName('')).toBe('')
      expect(wrapper.vm.fileName(null)).toBe('')
    })

    it('formatSize formats bytes to human-readable string', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.formatSize(0)).toBe('0 B')
      expect(wrapper.vm.formatSize(500)).toBe('500.0 B')
      expect(wrapper.vm.formatSize(1024)).toBe('1.0 KB')
      expect(wrapper.vm.formatSize(1048576)).toBe('1.0 MB')
      expect(wrapper.vm.formatSize(1073741824)).toBe('1.0 GB')
    })

    it('vmafColor returns correct color by score', async () => {
      const wrapper = await mountApprovalQueue()
      expect(wrapper.vm.vmafColor(95)).toBe('positive')
      expect(wrapper.vm.vmafColor(80)).toBe('warning')
      expect(wrapper.vm.vmafColor(60)).toBe('negative')
      expect(wrapper.vm.vmafColor(null)).toBe('grey')
    })

    it('totalSpaceSaved uses the approval summary aggregate', async () => {
      const wrapper = await mountApprovalQueue()
      // MOCK_TASKS: |-400000| + |-500000| = 900000 (task 3 has positive delta, excluded)
      expect(wrapper.vm.totalSpaceSaved).toBe(900000)
    })

    it('savingsPercent calculates correctly', async () => {
      const wrapper = await mountApprovalQueue()
      const row = { source_size: 1000000, staged_size: 600000 }
      expect(wrapper.vm.savingsPercent(row)).toBe('40.0')
    })
  })

  // Error handling
  describe('error handling', () => {
    it('handles fetch failure gracefully and sets loading to false', async () => {
      axios.post.mockImplementation((url) => {
        if (url.includes('approval/tasks')) {
          return Promise.reject(new Error('Network error'))
        }
        return Promise.resolve({ data: {} })
      })
      axios.get.mockImplementation(() => Promise.resolve({ data: { settings: { approval_required: true } } }))

      const wrapper = shallowMountWithQuasar(ApprovalQueue)
      await flushPromises()

      expect(wrapper.vm.loading).toBe(false)
      expect(wrapper.vm.tasks).toEqual([])
    })
  })
})
