import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import axios from 'axios'
import { mountWithQuasar } from 'src/test-utils'
import SafetyStatusBanner from '../SafetyStatusBanner.vue'

/**
 * The safety latch is fail-closed and durable: when it trips, work is paused
 * until an operator reviews it. This banner is the only place that surfaces
 * that in the UI, so the states that matter are "shows when paused", "stays
 * showing when the API goes away", and "stops polling when unmounted".
 */

vi.mock('axios')

// The shared helper stubs q-btn anonymously; name it here so the review action
// can be located and its route asserted.
const btnStub = {
  name: 'QBtn',
  props: ['label', 'to', 'color', 'flat'],
  template: '<button class="q-btn">{{ label }}</button>',
}

const mountBanner = () => mountWithQuasar(SafetyStatusBanner, { global: { stubs: { 'q-btn': btnStub } } })

describe('SafetyStatusBanner', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(axios.get).mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('stays hidden while no pause is required', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { pause_required: false } })

    const wrapper = mountBanner()
    await flushPromises()

    expect(wrapper.find('[data-testid="global-safety-banner"]').exists()).toBe(false)
  })

  it('shows the banner when the safety latch has tripped', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { pause_required: true } })

    const wrapper = mountBanner()
    await flushPromises()

    expect(wrapper.find('[data-testid="global-safety-banner"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('pages.deploymentReadiness.globalPause')
  })

  it('offers a route to the readiness page for review', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { pause_required: true } })

    const wrapper = mountBanner()
    await flushPromises()

    const action = wrapper.findComponent({ name: 'QBtn' })
    expect(action.exists()).toBe(true)
    expect(action.props('to')).toBe('/ui/readiness')
  })

  it('keeps showing a tripped latch when the API stops responding', async () => {
    vi.mocked(axios.get).mockResolvedValueOnce({ data: { pause_required: true } })

    const wrapper = mountBanner()
    await flushPromises()
    expect(wrapper.find('[data-testid="global-safety-banner"]').exists()).toBe(true)

    // A dropped connection must not be read as "safe to resume".
    vi.mocked(axios.get).mockRejectedValue(new Error('network down'))
    await vi.advanceTimersByTimeAsync(15000)
    await flushPromises()

    expect(wrapper.find('[data-testid="global-safety-banner"]').exists()).toBe(true)
  })

  it('treats a missing pause_required field as not paused rather than crashing', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: {} })

    const wrapper = mountBanner()
    await flushPromises()

    expect(wrapper.find('[data-testid="global-safety-banner"]').exists()).toBe(false)
  })

  it('polls so a latch tripped after page load still surfaces', async () => {
    vi.mocked(axios.get).mockResolvedValueOnce({ data: { pause_required: false } })

    const wrapper = mountBanner()
    await flushPromises()
    expect(wrapper.find('[data-testid="global-safety-banner"]').exists()).toBe(false)

    vi.mocked(axios.get).mockResolvedValue({ data: { pause_required: true } })
    await vi.advanceTimersByTimeAsync(15000)
    await flushPromises()

    expect(wrapper.find('[data-testid="global-safety-banner"]').exists()).toBe(true)
  })

  it('stops polling once unmounted', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { pause_required: false } })

    const wrapper = mountBanner()
    await flushPromises()
    const callsWhileMounted = vi.mocked(axios.get).mock.calls.length

    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(60000)

    expect(vi.mocked(axios.get).mock.calls.length).toBe(callsWhileMounted)
  })
})
