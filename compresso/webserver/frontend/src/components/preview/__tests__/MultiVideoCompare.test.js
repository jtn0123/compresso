import { describe, expect, it, vi } from 'vitest'

vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({ dark: { isActive: false }, screen: { lt: { md: false } } }),
  Notify: { create: vi.fn() },
  Dialog: {},
  LocalStorage: { getItem: vi.fn(), setItem: vi.fn() },
  SessionStorage: { getItem: vi.fn(), setItem: vi.fn() },
}))

import { mountWithQuasar } from 'src/test-utils'
import MultiVideoCompare from '../MultiVideoCompare.vue'

const candidates = [
  {
    candidate_uuid: 'one',
    profile_label: 'x265 CRF 22',
    encoder: 'libx265',
    status: 'running',
    progress: 42,
  },
  {
    candidate_uuid: 'two',
    profile_label: 'SVT-AV1 CRF 30',
    encoder: 'libsvtav1',
    status: 'queued',
    progress: 0,
  },
  {
    candidate_uuid: 'three',
    profile_label: 'AMD AMF',
    encoder: 'hevc_amf',
    status: 'failed',
    progress: 15,
    error: 'Encoder unavailable',
  },
]

describe('MultiVideoCompare', () => {
  it('renders one independently progressing quadrant per candidate', () => {
    const wrapper = mountWithQuasar(MultiVideoCompare, { props: { candidates } })

    expect(wrapper.findAll('.candidate-cell')).toHaveLength(3)
    expect(wrapper.text()).toContain('42%')
    expect(wrapper.text()).toContain('Encoder unavailable')
  })

  it('marks the persisted winner in the contact sheet', () => {
    const completed = candidates.map((candidate) => ({
      ...candidate,
      status: 'completed',
      output_url: `/preview/${candidate.candidate_uuid}.mp4`,
    }))
    const wrapper = mountWithQuasar(MultiVideoCompare, {
      props: { candidates: completed, selectedCandidateUuid: 'two' },
    })

    expect(wrapper.findAll('.candidate-cell--winner')).toHaveLength(1)
  })

  it('supports keyboard frame review from the shared stage', async () => {
    const wrapper = mountWithQuasar(MultiVideoCompare, { props: { candidates } })

    await wrapper.find('.comparison-stage').trigger('keydown', { key: 'ArrowRight' })

    expect(wrapper.find('.candidate-cell--frozen').exists()).toBe(true)
  })
})
