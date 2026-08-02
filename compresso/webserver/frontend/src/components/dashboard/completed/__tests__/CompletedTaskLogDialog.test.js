import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import axios from 'axios'
import { mountWithQuasar } from 'src/test-utils'
import CompletedTaskLogDialog from '../CompletedTaskLogDialog.vue'

/**
 * This dialog renders encoder log lines through `v-html` so ANSI colouring
 * survives. That makes it one of the eight places in the UI where server data
 * becomes markup, and the log content describes files whose names the user does
 * not control.
 *
 * The component's own responsibility is routing EVERY line through
 * `sanitizeHtml` before it reaches `v-html` — that is what these tests pin.
 * Whether the sanitiser strips a given payload is DOMPurify's contract and is
 * covered by `src/js/__tests__/sanitize.test.js`; asserting on rendered markup
 * here would instead be testing the test environment's DOM implementation.
 */

vi.mock('axios')

const sanitizeHtml = vi.fn((value) => `SANITIZED:${value}`)
vi.mock('src/js/sanitize', () => ({ sanitizeHtml: (value) => sanitizeHtml(value) }))

const notify = vi.fn()
// The component reaches for $q through useQuasar(), which needs the real Quasar
// plugin; the shared mount helper deliberately does not install it.
vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({ notify, dark: { isActive: false } }),
}))

const dialogStub = {
  name: 'CompressoDialogWindow',
  template: '<div class="dialog-window"><slot /></div>',
  methods: {
    show() {},
    hide() {},
  },
}

const mountDialog = () =>
  mountWithQuasar(CompletedTaskLogDialog, {
    props: { completedTaskId: '7' },
    stubs: {
      CompressoDialogWindow: dialogStub,
      'q-scroll-area': { template: '<div><slot /></div>' },
    },
  })

const respondWith = (lines) => {
  vi.mocked(axios).mockResolvedValue({ data: { command_log_lines: lines } })
}

describe('CompletedTaskLogDialog', () => {
  beforeEach(() => {
    sanitizeHtml.mockClear()
    notify.mockClear()
  })

  it('renders one paragraph per returned log line', async () => {
    respondWith(['first line', 'second line'])

    const wrapper = mountDialog()
    await flushPromises()

    const paragraphs = wrapper.findAll('.completed-task-details-dialog-content p')
    expect(paragraphs).toHaveLength(2)
  })

  it('sanitises every log line before it reaches v-html', async () => {
    respondWith(['first line', '<span style="color: red">ffmpeg error</span>', 'third line'])

    mountDialog()
    await flushPromises()

    expect(sanitizeHtml).toHaveBeenCalledTimes(3)
    expect(sanitizeHtml.mock.calls.map(([value]) => value)).toEqual([
      'first line',
      '<span style="color: red">ffmpeg error</span>',
      'third line',
    ])
  })

  it('renders the sanitiser output rather than the raw response', async () => {
    respondWith(['before<script>window.stolen = 1</script>after'])

    const wrapper = mountDialog()
    await flushPromises()

    // The stub marks its output, proving nothing bypasses the sanitiser on the
    // way to v-html.
    expect(wrapper.find('.completed-task-details-dialog-content').html()).toContain('SANITIZED:')
  })

  it('sanitises even a single hostile-looking line', async () => {
    respondWith(['<img src="x" onerror="window.stolen = 1">'])

    mountDialog()
    await flushPromises()

    expect(sanitizeHtml).toHaveBeenCalledExactlyOnceWith('<img src="x" onerror="window.stolen = 1">')
  })

  it('renders nothing when the API returns a non-array log payload', async () => {
    respondWith({ unexpected: 'shape' })

    const wrapper = mountDialog()
    await flushPromises()

    expect(wrapper.findAll('.completed-task-details-dialog-content p')).toHaveLength(0)
  })

  it('notifies instead of throwing when the log request fails', async () => {
    notify.mockClear()
    vi.mocked(axios).mockRejectedValue(new Error('boom'))

    const wrapper = mountDialog()
    await flushPromises()

    expect(notify).toHaveBeenCalledTimes(1)
    expect(notify.mock.calls[0][0]).toMatchObject({ color: 'negative' })
    expect(wrapper.findAll('.completed-task-details-dialog-content p')).toHaveLength(0)
  })

  it('requests the log for the task it was given', async () => {
    respondWith([])

    mountDialog()
    await flushPromises()

    expect(vi.mocked(axios).mock.calls[0][0]).toMatchObject({
      method: 'post',
      data: { task_id: 7 },
    })
  })
})
