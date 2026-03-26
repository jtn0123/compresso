import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({
    notify: vi.fn(),
    dark: { isActive: false },
    screen: {
      gt: { xs: true, sm: true },
      lt: { sm: false, md: false },
    },
  }),
  Notify: { create: vi.fn() },
}))

// Mock chart.js to avoid canvas rendering in tests
vi.mock('chart.js', () => {
  class ChartMock {
    constructor() {
      this.destroy = vi.fn()
      this.update = vi.fn()
    }
  }
  ChartMock.register = vi.fn()
  return {
    Chart: ChartMock,
    LineController: {},
    LineElement: {},
    PointElement: {},
    CategoryScale: {},
    LinearScale: {},
    Tooltip: {},
    Legend: {},
  }
})

import { shallowMountWithQuasar } from 'src/test-utils'
import GpuUtilizationChart from '../GpuUtilizationChart.vue'

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GpuUtilizationChart.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // 1. Renders "No GPU data" when history is empty
  describe('empty state', () => {
    it('shows no-data message when gpuHistory is empty object', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: { gpuHistory: {} },
      })
      expect(wrapper.vm.hasData).toBe(false)
    })

    it('shows no-data message when gpuHistory is not provided', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart)
      expect(wrapper.vm.hasData).toBe(false)
    })

    it('shows no-data when all gpu arrays are empty', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: { gpuHistory: { 0: [], 1: [] } },
      })
      expect(wrapper.vm.hasData).toBe(false)
    })
  })

  // 2. Renders canvas element when history has data
  describe('with data', () => {
    const gpuHistoryWithData = {
      0: [
        { timestamp: 1700000000, gpu_name: 'NVIDIA RTX 4090', utilization_percent: 85, temperature_c: 72 },
        { timestamp: 1700000060, gpu_name: 'NVIDIA RTX 4090', utilization_percent: 90, temperature_c: 74 },
      ],
    }

    it('hasData is true when gpuHistory has points', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: { gpuHistory: gpuHistoryWithData },
      })
      expect(wrapper.vm.hasData).toBe(true)
    })

    it('renders a canvas element when data is present', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: { gpuHistory: gpuHistoryWithData },
      })
      expect(wrapper.find('canvas').exists()).toBe(true)
    })
  })

  // 3. Props are received correctly
  describe('props', () => {
    it('receives gpuHistory prop', () => {
      const gpuHistory = {
        0: [{ timestamp: 1700000000, gpu_name: 'GPU0', utilization_percent: 50, temperature_c: 60 }],
      }
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: { gpuHistory },
      })
      expect(wrapper.props('gpuHistory')).toEqual(gpuHistory)
    })

    it('gpuHistory defaults to empty object', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart)
      expect(wrapper.props('gpuHistory')).toEqual({})
    })
  })

  // 4. Handles dark mode prop/detection
  describe('dark mode', () => {
    it('renders correctly with dark mode active', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: {
          gpuHistory: {
            0: [{ timestamp: 1700000000, gpu_name: 'GPU0', utilization_percent: 50, temperature_c: 60 }],
          },
        },
        global: {
          mocks: {
            $q: {
              notify: vi.fn(),
              dark: { isActive: true },
              screen: {
                gt: { xs: true, sm: true },
                lt: { sm: false, md: false },
              },
            },
          },
        },
      })
      expect(wrapper.vm.hasData).toBe(true)
      expect(wrapper.find('canvas').exists()).toBe(true)
    })
  })

  // Edge cases
  describe('edge cases', () => {
    it('handles null gpuHistory gracefully', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: { gpuHistory: null },
      })
      expect(wrapper.vm.hasData).toBe(false)
    })

    it('handles non-object gpuHistory gracefully', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: { gpuHistory: 'invalid' },
      })
      expect(wrapper.vm.hasData).toBe(false)
    })

    it('hasData is true when at least one GPU has data points', () => {
      const wrapper = shallowMountWithQuasar(GpuUtilizationChart, {
        props: {
          gpuHistory: {
            0: [],
            1: [{ timestamp: 1700000000, gpu_name: 'GPU1', utilization_percent: 30, temperature_c: 55 }],
          },
        },
      })
      expect(wrapper.vm.hasData).toBe(true)
    })
  })
})
