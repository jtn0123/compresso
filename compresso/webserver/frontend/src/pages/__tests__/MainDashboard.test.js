import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

// ---------------------------------------------------------------------------
// Mocks — vi.mock factories are hoisted and must not reference outer variables
// ---------------------------------------------------------------------------

vi.mock('axios', () => {
  const fn = vi.fn(() => Promise.resolve({ data: {} }))
  fn.get = vi.fn(() => Promise.resolve({ data: {} }))
  fn.post = vi.fn(() => Promise.resolve({ data: {} }))
  fn.delete = vi.fn(() => Promise.resolve({ data: {} }))
  return { default: fn }
})

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

vi.mock('src/js/compressoWebsocket', () => ({
  CompressoWebsocketHandler: () => ({
    init: vi.fn(() => ({ readyState: 1, send: vi.fn() })),
    close: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }),
}))

vi.mock('src/composables/useSystemStatus', async () => {
  const { ref } = await import('vue')
  return {
    useSystemStatus: () => ({
      systemInfo: ref(null),
      liveMetrics: ref({
        cpu_percent: 0,
        memory_percent: 0,
        memory_used_gb: 0,
        disk_percent: 0,
        disk_used_gb: 0,
        gpus: [],
      }),
      gpuHistory: ref([]),
      fetchSystemInfo: vi.fn(() => Promise.resolve()),
      startLiveMetrics: vi.fn(),
      stopLiveMetrics: vi.fn(),
      updateLiveMetrics: vi.fn(),
    }),
  }
})

vi.mock('src/composables/useWorkerGauges', () => ({
  useWorkerGauges: () => ({
    generateGroupColour: vi.fn(() => '#42b883'),
  }),
}))

vi.mock('src/js/dateTools', () => ({
  default: {
    printDateTimeString: vi.fn((ts) => new Date(ts * 1000).toISOString()),
    printSecondsAsDuration: vi.fn((s) => `${Math.floor(s)}s`),
  },
}))

import axios from 'axios'
import { shallowMountWithQuasar } from 'src/test-utils'
import MainDashboard from '../MainDashboard.vue'

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MainDashboard.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    axios.get.mockResolvedValue({ data: {} })
    axios.post.mockResolvedValue({ data: {} })
    axios.mockResolvedValue({ data: {} })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // 1. Renders without crashing
  it('renders without crashing', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
  })

  // 2. Shows system status bar
  it('renders the SystemStatusBar component', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()

    const statusBar = wrapper.findComponent({ name: 'SystemStatusBar' })
    expect(statusBar.exists()).toBe(true)
  })

  it('passes systemInfo and liveMetrics props to SystemStatusBar', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()

    const statusBar = wrapper.findComponent({ name: 'SystemStatusBar' })
    expect(statusBar.props('systemInfo')).toBeDefined()
    expect(statusBar.props('liveMetrics')).toBeDefined()
  })

  // 3. Worker cards render with data
  it('renders WorkersPanel component', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()

    const panel = wrapper.findComponent({ name: 'WorkersPanel' })
    expect(panel.exists()).toBe(true)
  })

  it('passes workerProgressList to WorkersPanel', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()

    const panel = wrapper.findComponent({ name: 'WorkersPanel' })
    expect(panel.props('workerProgressList')).toBeDefined()
  })

  // 4. Pending tasks section displays
  it('renders PendingTasks component', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()

    const pending = wrapper.findComponent({ name: 'PendingTasks' })
    expect(pending.exists()).toBe(true)
  })

  it('renders CompletedTasks component', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()

    const completed = wrapper.findComponent({ name: 'CompletedTasks' })
    expect(completed.exists()).toBe(true)
  })

  // 5. Queue ETA displays when data available
  it('passes queueEta to PendingTasks', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()

    const pending = wrapper.findComponent({ name: 'PendingTasks' })
    expect(pending.props('queueEta')).toBeDefined()
  })

  it('queueEta starts as null', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()
    expect(wrapper.vm.queueEta).toBeNull()
  })

  // 6. GPU card shows when GPUs detected
  it('does not show GPU section when no GPUs are present', async () => {
    const wrapper = shallowMountWithQuasar(MainDashboard)
    await flushPromises()

    // GpuUtilizationChart is wrapped in a v-if on liveMetrics.gpus.length > 0
    const gpuChart = wrapper.findComponent({ name: 'GpuUtilizationChart' })
    expect(gpuChart.exists()).toBe(false)
  })

  // 7. Dashboard sub-components render
  describe('sub-components', () => {
    it('renders LibraryDonutChart', async () => {
      const wrapper = shallowMountWithQuasar(MainDashboard)
      await flushPromises()

      const chart = wrapper.findComponent({ name: 'LibraryDonutChart' })
      expect(chart.exists()).toBe(true)
    })

    it('renders CompactStatsGrid', async () => {
      const wrapper = shallowMountWithQuasar(MainDashboard)
      await flushPromises()

      const grid = wrapper.findComponent({ name: 'CompactStatsGrid' })
      expect(grid.exists()).toBe(true)
    })

    it('renders LinkedNodesPanel', async () => {
      const wrapper = shallowMountWithQuasar(MainDashboard)
      await flushPromises()

      const panel = wrapper.findComponent({ name: 'LinkedNodesPanel' })
      expect(panel.exists()).toBe(true)
    })

    it('renders HealthCheckPanel', async () => {
      const wrapper = shallowMountWithQuasar(MainDashboard)
      await flushPromises()

      const panel = wrapper.findComponent({ name: 'HealthCheckPanel' })
      expect(panel.exists()).toBe(true)
    })
  })

  // Optimization data
  describe('optimization data', () => {
    it('starts with loading state for optimization', async () => {
      axios.get.mockImplementation(() => new Promise(() => {}))
      const wrapper = shallowMountWithQuasar(MainDashboard)
      expect(wrapper.vm.optimizationData.loading).toBe(true)
    })

    it('fetches optimization progress on mount', async () => {
      axios.get.mockResolvedValue({
        data: { total: 100, processed: 42, percent: 42 },
      })
      const wrapper = shallowMountWithQuasar(MainDashboard)
      await flushPromises()

      expect(wrapper.vm.optimizationData.totalFiles).toBe(100)
      expect(wrapper.vm.optimizationData.processedFiles).toBe(42)
      expect(wrapper.vm.optimizationData.percent).toBe(42)
      expect(wrapper.vm.optimizationData.loading).toBe(false)
    })
  })

  // Worker actions
  describe('worker actions', () => {
    it('pauseAllWorkers posts to the correct endpoint', async () => {
      const wrapper = shallowMountWithQuasar(MainDashboard)
      await flushPromises()

      wrapper.vm.pauseAllWorkers()
      await flushPromises()

      expect(axios).toHaveBeenCalledWith(
        expect.objectContaining({
          method: 'post',
          url: expect.stringContaining('workers/worker/pause/all'),
        }),
      )
    })

    it('resumeAllWorkers posts to the correct endpoint', async () => {
      const wrapper = shallowMountWithQuasar(MainDashboard)
      await flushPromises()

      wrapper.vm.resumeAllWorkers()
      await flushPromises()

      expect(axios).toHaveBeenCalledWith(
        expect.objectContaining({
          method: 'post',
          url: expect.stringContaining('workers/worker/resume/all'),
        }),
      )
    })
  })

  // Stale data warning
  describe('stale data warning', () => {
    it('workersStale starts as false', async () => {
      const wrapper = shallowMountWithQuasar(MainDashboard)
      await flushPromises()

      expect(wrapper.vm.workersStale).toBe(false)
    })
  })
})
