import { describe, expect, it, vi } from 'vitest'
import { mountWithQuasar } from 'src/test-utils'
import CompressoDialogConfirm from '../CompressoDialogConfirm.vue'

/**
 * This dialog is the gate in front of every destructive action in the UI —
 * removing a library, discarding a staged encode, deleting a worker group. If
 * confirm and cancel are ever wired to the same handler, or the dialog stays
 * open after a choice, a user destroys something they did not agree to.
 */

const dialogStub = {
  name: 'QDialog',
  emits: ['hide'],
  props: ['persistent'],
  template: '<div class="q-dialog"><slot /></div>',
  methods: {
    show() {
      this.shown = true
    },
    hide() {
      this.shown = false
      this.$emit('hide')
    },
  },
  data() {
    return { shown: false }
  },
}

const btnStub = {
  name: 'QBtn',
  props: ['label', 'color', 'outline'],
  emits: ['click'],
  template: '<button class="q-btn" @click="$emit(\'click\')">{{ label }}</button>',
}

const mountDialog = (props = {}, slots = {}) =>
  mountWithQuasar(CompressoDialogConfirm, {
    props,
    slots,
    global: { stubs: { 'q-dialog': dialogStub, 'q-btn': btnStub } },
  })

const buttonLabelled = (wrapper, label) =>
  wrapper.findAllComponents({ name: 'QBtn' }).find((button) => button.props('label') === label)

describe('CompressoDialogConfirm', () => {
  it('emits confirm only when the confirm button is pressed', async () => {
    const wrapper = mountDialog()

    await buttonLabelled(wrapper, 'navigation.yes').trigger('click')

    expect(wrapper.emitted('confirm')).toHaveLength(1)
    expect(wrapper.emitted('cancel')).toBeUndefined()
  })

  it('emits cancel only when the cancel button is pressed', async () => {
    const wrapper = mountDialog()

    await buttonLabelled(wrapper, 'navigation.cancel').trigger('click')

    expect(wrapper.emitted('cancel')).toHaveLength(1)
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })

  it('closes itself after either choice so a second click cannot re-fire it', async () => {
    const wrapper = mountDialog()
    const dialog = wrapper.findComponent({ name: 'QDialog' })
    dialog.vm.show()
    expect(dialog.vm.shown).toBe(true)

    await buttonLabelled(wrapper, 'navigation.yes').trigger('click')

    expect(dialog.vm.shown).toBe(false)
  })

  it('closes itself on cancel as well', async () => {
    const wrapper = mountDialog()
    const dialog = wrapper.findComponent({ name: 'QDialog' })
    dialog.vm.show()

    await buttonLabelled(wrapper, 'navigation.cancel').trigger('click')

    expect(dialog.vm.shown).toBe(false)
  })

  it('re-emits hide so callers can clean up their dialog instance', async () => {
    const wrapper = mountDialog()

    await wrapper.findComponent({ name: 'QDialog' }).vm.$emit('hide')

    expect(wrapper.emitted('hide')).toHaveLength(1)
  })

  it('is persistent by default so a stray backdrop click cannot dismiss it', () => {
    const wrapper = mountDialog()

    expect(wrapper.findComponent({ name: 'QDialog' }).props('persistent')).toBe(true)
  })

  it('uses caller-supplied labels and message when given', () => {
    const wrapper = mountDialog({
      title: 'Delete library',
      message: 'This removes every task for the library.',
      okLabel: 'Delete',
      cancelLabel: 'Keep',
    })

    expect(wrapper.text()).toContain('Delete library')
    expect(wrapper.text()).toContain('This removes every task for the library.')
    expect(buttonLabelled(wrapper, 'Delete')).toBeTruthy()
    expect(buttonLabelled(wrapper, 'Keep')).toBeTruthy()
  })

  it('falls back to translated labels when the caller supplies none', () => {
    const wrapper = mountDialog()

    expect(wrapper.text()).toContain('headers.confirm')
    expect(buttonLabelled(wrapper, 'navigation.yes')).toBeTruthy()
    expect(buttonLabelled(wrapper, 'navigation.cancel')).toBeTruthy()
  })

  it('renders slot content in place of the default message', () => {
    const wrapper = mountDialog({}, { default: '<p class="custom">Custom warning</p>' })

    expect(wrapper.find('.custom').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('components.settings.library.confirmRemove')
  })

  it('exposes show and hide to the parent that owns the dialog', () => {
    const wrapper = mountDialog()
    const dialog = wrapper.findComponent({ name: 'QDialog' })
    const showSpy = vi.spyOn(dialog.vm, 'show')
    const hideSpy = vi.spyOn(dialog.vm, 'hide')

    wrapper.vm.show()
    wrapper.vm.hide()

    expect(showSpy).toHaveBeenCalled()
    expect(hideSpy).toHaveBeenCalled()
  })
})
