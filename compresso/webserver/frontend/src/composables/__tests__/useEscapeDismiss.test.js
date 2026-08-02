import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useEscapeDismiss } from '../useEscapeDismiss'

/**
 * Quasar's addEscapeKey is a no-op unless Platform.is.desktop, so no QDialog
 * reacts to Escape on a touch-capable viewport. This composable fills that gap
 * without double-handling on desktop.
 */

let isDesktop = false
vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({ platform: { is: { desktop: isDesktop } } }),
}))

const harness = (dismiss) =>
  defineComponent({
    setup(_props, { expose }) {
      expose(useEscapeDismiss(dismiss))
      return () => h('div')
    },
  })

const mountHarness = (dismiss) => mount(harness(dismiss))

const pressEscape = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
const pressOtherKey = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))

describe('useEscapeDismiss', () => {
  beforeEach(() => {
    isDesktop = false
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('dismisses on Escape where Quasar does not handle it', async () => {
    const dismiss = vi.fn()
    const wrapper = mountHarness(dismiss)
    wrapper.vm.activate()

    pressEscape()

    expect(dismiss).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('stays out of the way on desktop, where Quasar already handles Escape', () => {
    isDesktop = true
    const dismiss = vi.fn()
    const wrapper = mountHarness(dismiss)
    wrapper.vm.activate()

    pressEscape()

    expect(dismiss).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('ignores other keys', () => {
    const dismiss = vi.fn()
    const wrapper = mountHarness(dismiss)
    wrapper.vm.activate()

    pressOtherKey()

    expect(dismiss).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does nothing before activate or after deactivate', () => {
    const dismiss = vi.fn()
    const wrapper = mountHarness(dismiss)

    pressEscape()
    expect(dismiss).not.toHaveBeenCalled()

    wrapper.vm.activate()
    wrapper.vm.deactivate()
    pressEscape()

    expect(dismiss).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('dismisses only the top dialog when several are stacked', () => {
    const first = vi.fn()
    const second = vi.fn()
    const outer = mountHarness(first)
    const inner = mountHarness(second)
    outer.vm.activate()
    inner.vm.activate()

    pressEscape()
    expect(second).toHaveBeenCalledTimes(1)
    expect(first).not.toHaveBeenCalled()

    // Closing the top one hands Escape back to the one beneath it.
    inner.vm.deactivate()
    pressEscape()
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)

    outer.unmount()
    inner.unmount()
  })

  it('releases the listener when the component unmounts', () => {
    const dismiss = vi.fn()
    const wrapper = mountHarness(dismiss)
    wrapper.vm.activate()

    wrapper.unmount()
    pressEscape()

    expect(dismiss).not.toHaveBeenCalled()
  })

  it('activating twice registers only one handler', () => {
    const dismiss = vi.fn()
    const wrapper = mountHarness(dismiss)
    wrapper.vm.activate()
    wrapper.vm.activate()

    pressEscape()

    expect(dismiss).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
