import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: vi.fn((version, endpoint) => `/compresso/api/${version}/${endpoint}`),
}))
vi.mock('src/composables/useLogger', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))
vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({
    notify: vi.fn(),
    dark: { isActive: false },
    screen: { lt: { sm: false, md: false } },
  }),
  Notify: { create: vi.fn() },
  Dialog: {},
  LocalStorage: { getItem: vi.fn(), setItem: vi.fn() },
  SessionStorage: { getItem: vi.fn(), setItem: vi.fn() },
}))

import axios from 'axios'
import { shallowMountWithQuasar } from 'src/test-utils'
import SampleComparison from '../SampleComparison.vue'

const profiles = [
  { key: 'x265_crf_22', label: 'x265 CRF 22', encoder: 'libx265', codec: 'hevc', available: true },
  { key: 'svt_av1_crf_30', label: 'SVT-AV1 CRF 30', encoder: 'libsvtav1', codec: 'av1', available: true },
  {
    key: 'amd_amf_hevc_quality',
    label: 'AMD AMF HEVC',
    encoder: 'hevc_amf',
    codec: 'hevc',
    available: false,
  },
  { key: 'x264_crf_23', label: 'x264 CRF 23', encoder: 'libx264', codec: 'h264', available: true },
]

const completedStatus = {
  batch_uuid: 'batch-1',
  status: 'completed',
  progress: 100,
  winner_candidate_id: null,
  full_encode_task_id: null,
  candidates: [
    {
      id: 1,
      candidate_uuid: 'candidate-1',
      profile_key: 'x265_crf_22',
      profile_label: 'x265 CRF 22',
      encoder: 'libx265',
      codec: 'hevc',
      status: 'completed',
      progress: 100,
    },
    {
      id: 2,
      candidate_uuid: 'candidate-2',
      profile_key: 'svt_av1_crf_30',
      profile_label: 'SVT-AV1 CRF 30',
      encoder: 'libsvtav1',
      codec: 'av1',
      status: 'completed',
      progress: 100,
    },
  ],
}

function mockSetupAndStatus() {
  axios.get.mockImplementation((url) => {
    if (url.includes('comparison/profiles')) return Promise.resolve({ data: { profiles } })
    return Promise.resolve({
      data: { settings: { libraries: [{ id: 1, name: 'Movies', path: '/media/movies' }] } },
    })
  })
  axios.post.mockImplementation((url, body) => {
    if (url.includes('comparison/create')) return Promise.resolve({ data: { batch_uuid: 'batch-1' } })
    if (url.includes('comparison/status')) return Promise.resolve({ data: { ...completedStatus } })
    if (url.includes('comparison/winner')) {
      return Promise.resolve({
        data: {
          ...completedStatus,
          full_encode_task_id: body.queue_full_encode ? 42 : null,
        },
      })
    }
    return Promise.resolve({ data: { success: true } })
  })
}

describe('SampleComparison', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSetupAndStatus()
  })

  it('defaults to available software profiles and caps selection at four', async () => {
    const wrapper = shallowMountWithQuasar(SampleComparison)
    await flushPromises()

    expect(wrapper.vm.selectedProfileKeys).toEqual(['x265_crf_22', 'svt_av1_crf_30', 'x264_crf_23'])
    expect(wrapper.vm.selectedProfileKeys).not.toContain('amd_amf_hevc_quality')
  })

  it('creates a batch and polls its candidate status', async () => {
    const wrapper = shallowMountWithQuasar(SampleComparison)
    await flushPromises()
    wrapper.vm.sourcePath = '/media/movies/movie.mkv'

    await wrapper.vm.createComparison()
    await flushPromises()

    const createCall = axios.post.mock.calls.find(([url]) => url.includes('comparison/create'))
    expect(createCall[1].profile_keys).toHaveLength(3)
    expect(wrapper.vm.batch.status).toBe('completed')
    expect(wrapper.vm.batch.candidates).toHaveLength(2)
  })

  it('persists a winner before queueing the full encode', async () => {
    const wrapper = shallowMountWithQuasar(SampleComparison)
    await flushPromises()
    wrapper.vm.sourcePath = '/media/movies/movie.mkv'
    await wrapper.vm.createComparison()
    await wrapper.vm.selectWinner('candidate-1')
    await wrapper.vm.queueWinner()

    const winnerCalls = axios.post.mock.calls.filter(([url]) => url.includes('comparison/winner'))
    expect(winnerCalls[0][1].queue_full_encode).toBe(false)
    expect(winnerCalls[1][1].queue_full_encode).toBe(true)
    expect(wrapper.vm.batch.full_encode_task_id).toBe(42)
  })

  it('derives overall progress from the live candidate progress', async () => {
    const wrapper = shallowMountWithQuasar(SampleComparison)
    await flushPromises()
    wrapper.vm.batch = {
      status: 'running',
      progress: 5,
      candidates: [{ progress: 20 }, { progress: 60 }],
    }

    expect(wrapper.vm.batchProgress).toBe(40)
  })
})
