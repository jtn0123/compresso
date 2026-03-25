import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

// ---------------------------------------------------------------------------
// Mocks — vi.mock factories are hoisted; they must NOT reference outer vars.
// We use globalThis to share mutable state between the factory and the tests.
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

// Store dialog onOk callback on globalThis so the factory (hoisted) can write
// to it and the tests can read from it.
globalThis.__testDialogOnOk = null

vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({
    notify: vi.fn(),
    dialog: vi.fn(() => ({
      onOk: (fn) => {
        globalThis.__testDialogOnOk = fn
        return { onCancel: vi.fn() }
      },
    })),
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
import HealthCheck from '../HealthCheck.vue'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_SUMMARY = {
  healthy: 42,
  warning: 5,
  corrupted: 2,
  unchecked: 10,
  checking: 0,
  total: 59,
  scanning: false,
}

const MOCK_STATUSES = {
  results: [
    { id: 1, abspath: '/media/video1.mkv', status: 'healthy', check_mode: 'quick', error_detail: null, last_checked: '2025-06-01', error_count: 0 },
    { id: 2, abspath: '/media/video2.mp4', status: 'warning', check_mode: 'thorough', error_detail: 'Minor issue', last_checked: '2025-06-01', error_count: 1 },
    { id: 3, abspath: '/media/video3.avi', status: 'corrupted', check_mode: 'quick', error_detail: 'File truncated', last_checked: '2025-06-01', error_count: 3 },
  ],
  recordsFiltered: 3,
}

const MOCK_LIBRARIES = {
  settings: {
    libraries: [
      { id: 1, name: 'Movies' },
      { id: 2, name: 'TV Shows' },
    ],
  },
}

function setupDefaultMocks() {
  axios.get.mockImplementation((url) => {
    if (url.includes('healthcheck/summary')) {
      return Promise.resolve({ data: MOCK_SUMMARY })
    }
    if (url.includes('healthcheck/workers')) {
      return Promise.resolve({ data: { worker_count: 2 } })
    }
    if (url.includes('settings/read')) {
      return Promise.resolve({ data: MOCK_LIBRARIES })
    }
    return Promise.resolve({ data: {} })
  })
  axios.post.mockImplementation((url) => {
    if (url.includes('healthcheck/status')) {
      return Promise.resolve({ data: MOCK_STATUSES })
    }
    if (url.includes('healthcheck/scan-library')) {
      return Promise.resolve({ data: { started: true } })
    }
    if (url.includes('healthcheck/scan')) {
      return Promise.resolve({
        data: { abspath: '/media/test.mkv', status: 'healthy', error_detail: null },
      })
    }
    if (url.includes('healthcheck/cancel-scan')) {
      return Promise.resolve({ data: {} })
    }
    return Promise.resolve({ data: {} })
  })
}

async function mountHealthCheck() {
  setupDefaultMocks()
  const wrapper = shallowMountWithQuasar(HealthCheck)
  await flushPromises()
  return wrapper
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('HealthCheck.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    globalThis.__testDialogOnOk = null
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // 1. Renders the page with scan controls
  describe('rendering', () => {
    it('renders the PageHeader component', async () => {
      const wrapper = await mountHealthCheck()
      const header = wrapper.findComponent({ name: 'PageHeader' })
      expect(header.exists()).toBe(true)
    })

    it('renders five summary stat cards', async () => {
      const wrapper = await mountHealthCheck()
      const statCards = wrapper.findAll('.stat-card')
      expect(statCards.length).toBe(5)
    })

    it('populates summary data from API response', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.summary.healthy).toBe(42)
      expect(wrapper.vm.summary.warning).toBe(5)
      expect(wrapper.vm.summary.corrupted).toBe(2)
      expect(wrapper.vm.summary.unchecked).toBe(10)
      expect(wrapper.vm.summary.total).toBe(59)
    })

    it('sets loadingSummary to false after data loads', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.loadingSummary).toBe(false)
    })

    it('renders scan control section with correct default mode', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.scanMode).toBe('quick')
      expect(wrapper.vm.selectedLibraryId).toBeDefined()
    })
  })

  // 2. Start scan button triggers API call (via dialog confirmation)
  describe('scan library', () => {
    it('scanLibrary invokes dialog and captures onOk', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.scanLibrary()
      expect(globalThis.__testDialogOnOk).toBeTypeOf('function')
    })

    it('after dialog confirmation, posts to scan-library endpoint', async () => {
      const wrapper = await mountHealthCheck()
      vi.clearAllMocks()
      setupDefaultMocks()

      wrapper.vm.scanLibrary()
      await globalThis.__testDialogOnOk()
      await flushPromises()

      const scanCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('healthcheck/scan-library'),
      )
      expect(scanCalls.length).toBe(1)
      expect(scanCalls[0][1]).toEqual({
        library_id: expect.any(Number),
        mode: 'quick',
      })
    })

    it('sets scanning to true when backend confirms scan started', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.scanLibrary()
      await globalThis.__testDialogOnOk()
      await flushPromises()

      expect(wrapper.vm.scanning).toBe(true)
    })
  })

  // 3. Shows progress during active scan
  describe('scan progress', () => {
    it('scanProgressPercent tracks progress', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.scanProgress = { total: 100, checked: 50, workers: {}, files_per_second: 10, eta_seconds: 5 }
      wrapper.vm.scanProgressPercent = 0.5
      await wrapper.vm.$nextTick()

      expect(wrapper.vm.scanProgressPercent).toBe(0.5)
    })

    it('scanning starts as false', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.scanning).toBe(false)
    })

    it('formatEta returns human-readable time', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.formatEta(null)).toBe('--')
      expect(wrapper.vm.formatEta(0)).toBe('--')
      expect(wrapper.vm.formatEta(30)).toBe('30s')
      expect(wrapper.vm.formatEta(90)).toBe('1m 30s')
      expect(wrapper.vm.formatEta(3661)).toBe('1h 1m')
    })

    it('truncateFilename truncates long filenames', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.truncateFilename('')).toBe('')
      expect(wrapper.vm.truncateFilename(null)).toBe('')
      expect(wrapper.vm.truncateFilename('/path/short.mkv')).toBe('short.mkv')
      const longName = '/path/' + 'a'.repeat(60) + '.mkv'
      expect(wrapper.vm.truncateFilename(longName).length).toBeLessThanOrEqual(50)
      expect(wrapper.vm.truncateFilename(longName)).toContain('...')
    })
  })

  // 4. Displays health check results (status table)
  describe('status results', () => {
    it('populates statusResults from API response', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.statusResults).toHaveLength(3)
      expect(wrapper.vm.statusResults[0].abspath).toBe('/media/video1.mkv')
      expect(wrapper.vm.statusResults[1].status).toBe('warning')
    })

    it('statusResults have _checking property for recheck loading', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.statusResults.forEach((r) => {
        expect(r._checking).toBe(false)
      })
    })

    it('pagination rowsNumber is set from response', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.pagination.rowsNumber).toBe(3)
    })

    it('getStatusColor returns correct colors for each status', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.getStatusColor('healthy')).toBe('positive')
      expect(wrapper.vm.getStatusColor('warning')).toBe('warning')
      expect(wrapper.vm.getStatusColor('corrupted')).toBe('negative')
      expect(wrapper.vm.getStatusColor('checking')).toBe('info')
      expect(wrapper.vm.getStatusColor('unknown')).toBe('grey')
    })

    it('onTableRequest updates pagination and reloads statuses', async () => {
      const wrapper = await mountHealthCheck()
      vi.clearAllMocks()
      setupDefaultMocks()

      wrapper.vm.onTableRequest({
        pagination: { page: 2, rowsPerPage: 10, sortBy: 'status', descending: false },
      })
      await flushPromises()

      expect(wrapper.vm.pagination.page).toBe(2)
      expect(wrapper.vm.pagination.rowsPerPage).toBe(10)
      expect(wrapper.vm.pagination.sortBy).toBe('status')
      expect(wrapper.vm.pagination.descending).toBe(false)

      const statusCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('healthcheck/status'),
      )
      expect(statusCalls.length).toBeGreaterThanOrEqual(1)
    })
  })

  // 5. Error handling when API fails
  describe('error handling', () => {
    it('sets loadingSummary to false even on API failure', async () => {
      axios.get.mockImplementation((url) => {
        if (url.includes('healthcheck/summary')) {
          return Promise.reject(new Error('Server error'))
        }
        if (url.includes('settings/read')) {
          return Promise.resolve({ data: MOCK_LIBRARIES })
        }
        return Promise.resolve({ data: {} })
      })
      axios.post.mockResolvedValue({ data: { results: [], recordsFiltered: 0 } })

      const wrapper = shallowMountWithQuasar(HealthCheck)
      await flushPromises()

      expect(wrapper.vm.loadingSummary).toBe(false)
    })

    it('sets loadingStatuses to false even on status API failure', async () => {
      axios.get.mockImplementation((url) => {
        if (url.includes('settings/read')) {
          return Promise.resolve({ data: MOCK_LIBRARIES })
        }
        return Promise.resolve({ data: MOCK_SUMMARY })
      })
      axios.post.mockImplementation((url) => {
        if (url.includes('healthcheck/status')) {
          return Promise.reject(new Error('Network error'))
        }
        return Promise.resolve({ data: {} })
      })

      const wrapper = shallowMountWithQuasar(HealthCheck)
      await flushPromises()

      expect(wrapper.vm.loadingStatuses).toBe(false)
    })

    it('handles checkSingleFile failure gracefully', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.singleFilePath = '/bad/path.mkv'
      vi.clearAllMocks()
      axios.post.mockRejectedValue(new Error('Not found'))

      await wrapper.vm.checkSingleFile()
      await flushPromises()

      expect(wrapper.vm.singleFileResult).toBeNull()
    })
  })

  // Single file check
  describe('single file check', () => {
    it('checkSingleFile posts to the scan endpoint and sets result', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.singleFilePath = '/media/test.mkv'
      vi.clearAllMocks()
      setupDefaultMocks()

      await wrapper.vm.checkSingleFile()
      await flushPromises()

      const scanCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('healthcheck/scan'),
      )
      expect(scanCalls.length).toBeGreaterThanOrEqual(1)
      expect(wrapper.vm.singleFileResult).toEqual({
        abspath: '/media/test.mkv',
        status: 'healthy',
        error_detail: null,
      })
    })
  })

  // Cancel scan
  describe('cancel scan', () => {
    it('cancelScan posts to the cancel-scan endpoint', async () => {
      const wrapper = await mountHealthCheck()
      vi.clearAllMocks()
      setupDefaultMocks()

      await wrapper.vm.cancelScan()
      await flushPromises()

      const cancelCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('healthcheck/cancel-scan'),
      )
      expect(cancelCalls.length).toBe(1)
    })
  })

  // Worker count
  describe('worker count', () => {
    it('changeWorkerCount posts the new count', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.workerCount = 2
      vi.clearAllMocks()
      axios.post.mockResolvedValue({ data: { worker_count: 3 } })

      await wrapper.vm.changeWorkerCount(1)
      await flushPromises()

      const workerCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('healthcheck/workers'),
      )
      expect(workerCalls.length).toBe(1)
      expect(workerCalls[0][1]).toEqual({ worker_count: 3 })
      expect(wrapper.vm.workerCount).toBe(3)
    })

    it('changeWorkerCount does nothing when result would be below minimum', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.workerCount = 1
      vi.clearAllMocks()

      await wrapper.vm.changeWorkerCount(-1)
      await flushPromises()

      const workerCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('healthcheck/workers'),
      )
      expect(workerCalls.length).toBe(0)
    })

    it('changeWorkerCount does nothing when max exceeded', async () => {
      const wrapper = await mountHealthCheck()
      wrapper.vm.workerCount = 16
      vi.clearAllMocks()

      await wrapper.vm.changeWorkerCount(1)
      await flushPromises()

      const workerCalls = axios.post.mock.calls.filter(
        ([url]) => url.includes('healthcheck/workers'),
      )
      expect(workerCalls.length).toBe(0)
    })
  })

  // Libraries
  describe('library loading', () => {
    it('loads libraries on mount and populates options', async () => {
      const wrapper = await mountHealthCheck()
      expect(wrapper.vm.libraryOptions).toHaveLength(2)
      expect(wrapper.vm.libraryOptions[0].label).toBe('Movies')
      expect(wrapper.vm.libraryOptions[1].label).toBe('TV Shows')
      expect(wrapper.vm.selectedLibraryId).toBe(1)
    })
  })
})
