import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountWithQuasar } from 'src/test-utils'
import JsonImportExportDialog from '../JsonImportExportDialog.vue'

/**
 * This dialog is how a library's whole plugin-flow configuration gets replaced
 * in one paste. The guarantees worth pinning are that malformed JSON never
 * reaches the caller, that the submit action stays disabled until there is
 * something to submit, and that a half-typed import cannot be dismissed by a
 * stray backdrop click.
 */

const notify = vi.fn()
const copyToClipboard = vi.fn(() => Promise.resolve())
vi.mock('quasar', () => ({
  Quasar: { install() {} },
  copyToClipboard: (value) => copyToClipboard(value),
  useQuasar: () => ({ notify, dark: { isActive: false } }),
}))

const popupStub = {
  name: 'CompressoDialogPopup',
  props: ['title', 'persistent', 'actions'],
  emits: ['hide', 'copy', 'submit'],
  template: '<div class="popup"><slot /></div>',
  methods: {
    show() {},
    hide() {
      this.$emit('hide')
    },
  },
}

const mountDialog = (props = {}) =>
  mountWithQuasar(JsonImportExportDialog, {
    props: {
      dialogHeader: 'Library configuration',
      jsonData: '{"library":1}',
      mode: 'export',
      ...props,
    },
    stubs: {
      CompressoDialogPopup: popupStub,
      'q-input': {
        props: ['modelValue'],
        emits: ['update:modelValue'],
        template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
      },
    },
  })

const popup = (wrapper) => wrapper.findComponent({ name: 'CompressoDialogPopup' })
const submitAction = (wrapper) =>
  popup(wrapper)
    .props('actions')
    .find((action) => action.emit === 'submit')

describe('JsonImportExportDialog', () => {
  beforeEach(() => {
    notify.mockClear()
    copyToClipboard.mockClear()
    copyToClipboard.mockImplementation(() => Promise.resolve())
  })

  describe('import mode', () => {
    const importProps = { mode: 'import', jsonData: '' }

    it('keeps submit disabled until something is pasted', () => {
      const wrapper = mountDialog(importProps)

      expect(submitAction(wrapper).disabled).toBe(true)
    })

    it('keeps submit disabled for whitespace-only input', async () => {
      const wrapper = mountDialog(importProps)

      await wrapper.find('textarea').setValue('   \n  ')

      expect(submitAction(wrapper).disabled).toBe(true)
    })

    it('enables submit once real content is pasted', async () => {
      const wrapper = mountDialog(importProps)

      await wrapper.find('textarea').setValue('{"a":1}')

      expect(submitAction(wrapper).disabled).toBe(false)
    })

    it('hands valid JSON to the caller', async () => {
      const wrapper = mountDialog(importProps)
      await wrapper.find('textarea').setValue('{"plugins":["x"]}')

      await popup(wrapper).vm.$emit('submit')

      expect(wrapper.emitted('ok')).toHaveLength(1)
      expect(wrapper.emitted('ok')[0][0]).toEqual({ importString: '{"plugins":["x"]}' })
    })

    it('refuses malformed JSON instead of passing it on', async () => {
      const wrapper = mountDialog(importProps)
      await wrapper.find('textarea').setValue('{"plugins": [oops')

      await popup(wrapper).vm.$emit('submit')

      expect(wrapper.emitted('ok')).toBeUndefined()
      expect(notify).toHaveBeenCalledTimes(1)
      expect(notify.mock.calls[0][0]).toMatchObject({ color: 'negative' })
    })

    it('becomes persistent once there is unsaved input', async () => {
      const wrapper = mountDialog(importProps)
      expect(popup(wrapper).props('persistent')).toBe(false)

      await wrapper.find('textarea').setValue('{"a":1}')

      expect(popup(wrapper).props('persistent')).toBe(true)
    })
  })

  describe('export mode', () => {
    it('shows the configuration and offers only a copy action', () => {
      const wrapper = mountDialog()

      expect(wrapper.text()).toContain('{"library":1}')
      const actions = popup(wrapper).props('actions')
      expect(actions).toHaveLength(1)
      expect(actions[0].emit).toBe('copy')
    })

    it('is never persistent, because there is nothing to lose', () => {
      const wrapper = mountDialog()

      expect(popup(wrapper).props('persistent')).toBe(false)
    })

    it('copies the exported configuration and confirms', async () => {
      const wrapper = mountDialog()

      await popup(wrapper).vm.$emit('copy')
      await flushPromises()

      expect(copyToClipboard).toHaveBeenCalledWith('{"library":1}')
      expect(notify.mock.calls[0][0]).toMatchObject({ color: 'secondary' })
    })

    it('reports a blocked clipboard rather than failing silently', async () => {
      copyToClipboard.mockImplementation(() => Promise.reject(new Error('denied')))
      const wrapper = mountDialog()

      await popup(wrapper).vm.$emit('copy')
      await flushPromises()

      expect(notify.mock.calls[0][0]).toMatchObject({ color: 'negative' })
    })
  })

  it('re-emits hide so the parent can drop the dialog instance', async () => {
    const wrapper = mountDialog()

    await popup(wrapper).vm.$emit('hide')

    expect(wrapper.emitted('hide')).toHaveLength(1)
  })
})
