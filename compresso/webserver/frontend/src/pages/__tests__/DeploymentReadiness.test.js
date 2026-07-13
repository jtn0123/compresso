import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: vi.fn((version, endpoint) => `/compresso/api/${version}/${endpoint}`),
}))

import axios from 'axios'
import { mountWithQuasar } from 'src/test-utils'
import DeploymentReadiness from '../DeploymentReadiness.vue'

const readiness = {
  ready: false,
  doctor_report_expired: false,
  doctor_report: {
    overall_status: 'pass',
    generated_at: '2026-07-12T12:00:00Z',
    expires_at: '2026-07-13T12:00:00Z',
    checks: [{ id: 'cache', status: 'pass', summary: 'Cache is writable' }],
  },
  safety: {
    pause_required: true,
    events: [
      {
        id: 'event-1',
        code: 'disk-reserve',
        message: 'Cache reserve breached',
        active: true,
        acknowledged_at: null,
        first_seen_at: '2026-07-12T12:10:00Z',
      },
    ],
  },
}

describe('DeploymentReadiness', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    axios.get.mockResolvedValue({ data: readiness })
    axios.post.mockResolvedValue({ data: { ...readiness.safety, pause_required: false, events: [] } })
  })

  it('shows the deployment gate and durable safety event', async () => {
    const wrapper = mountWithQuasar(DeploymentReadiness)
    await flushPromises()

    expect(wrapper.get('[data-testid="deployment-gate"]').text()).toContain('pages.deploymentReadiness.notReady')
    expect(wrapper.get('[data-testid="safety-event-event-1"]').text()).toContain('Cache reserve breached')
    expect(wrapper.get('[data-testid="doctor-check-cache"]').text()).toContain('Cache is writable')
  })

  it('acknowledges an event then refreshes readiness', async () => {
    const wrapper = mountWithQuasar(DeploymentReadiness)
    await flushPromises()

    await wrapper.get('[data-testid="acknowledge-event-1"]').trigger('click')
    await flushPromises()

    expect(axios.post).toHaveBeenCalledWith('/compresso/api/v2/system/safety/acknowledge', {
      event_id: 'event-1',
      actor: 'operator',
    })
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it('requests a guarded worker resume', async () => {
    const wrapper = mountWithQuasar(DeploymentReadiness)
    await flushPromises()

    await wrapper.get('[data-testid="resume-workers"]').trigger('click')

    expect(axios.post).toHaveBeenCalledWith('/compresso/api/v2/system/safety/resume', {})
  })
})
