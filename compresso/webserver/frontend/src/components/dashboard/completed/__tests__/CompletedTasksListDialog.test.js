import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const quasar = vi.hoisted(() => ({
  notify: vi.fn(),
  dialog: vi.fn(),
}))

vi.mock('axios', () => ({ default: vi.fn() }))
vi.mock('quasar', () => ({
  useQuasar: () => ({
    ...quasar,
    screen: {
      width: 1024,
      height: 900,
      lt: { md: false },
      gt: { xs: true },
    },
  }),
}))
vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: (_version, endpoint) => `/api/${endpoint}`,
}))
vi.mock('src/js/dateTools', () => ({
  default: { printDateTimeString: (value) => `date:${value}` },
}))
vi.mock('src/composables/useMobile', () => ({
  useMobile: () => ({ isMobile: false }),
}))

import axios from 'axios'
import { shallowMountWithQuasar } from 'src/test-utils'
import CompletedTasksListDialog from '../CompletedTasksListDialog.vue'

const slotStub = { template: '<div><slot /></div>' }
const taskShellStub = {
  props: ['rows'],
  template: '<div><slot v-for="row in rows" name="body" :row="row" /></div>',
}
const mountCompletedDialog = (props = {}) =>
  shallowMountWithQuasar(CompletedTasksListDialog, {
    props,
    global: {
      stubs: {
        CompressoDialogWindow: slotStub,
        CompressoStandardButtonDropdown: slotStub,
        TaskListTableShell: taskShellStub,
        'q-slide-transition': slotStub,
      },
    },
  })

const makeTasks = (start, count, hasMetadata = false) =>
  Array.from({ length: count }, (_, index) => ({
    id: start + index,
    task_label: `File ${start + index}`,
    finish_time: 1000 + start + index,
    task_success: (start + index) % 2 === 1,
    has_metadata: hasMetadata,
  }))

const taskResponse = (results, total = results.length) => ({
  data: { results, recordsFiltered: total },
})

function state(wrapper) {
  return wrapper.vm.$.setupState
}

async function mountDialog({ tasks = makeTasks(1, 2), total = tasks.length, props = {} } = {}) {
  axios.mockImplementation(({ method, url }) => {
    if (method === 'post' && url === '/api/history/tasks') return Promise.resolve(taskResponse(tasks, total))
    return Promise.resolve({ data: {} })
  })
  const wrapper = mountCompletedDialog(props)
  await flushPromises()
  return wrapper
}

describe('CompletedTasksListDialog interactions', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads and maps the first completed-task page', async () => {
    const wrapper = await mountDialog()
    const vm = state(wrapper)

    expect(vm.rows[0]).toEqual({
      id: 1,
      name: 'File 1',
      dateTimeCompleted: 'date:1001',
      status: true,
      hasMetadata: false,
    })
    expect(vm.loading).toBe(false)
  })

  it('applies the initial status filter to requests', async () => {
    await mountDialog({ props: { initStatusFilter: 'failed' } })

    expect(axios).toHaveBeenCalledWith(
      expect.objectContaining({
        url: '/api/history/tasks',
        data: expect.objectContaining({ status: 'failed' }),
      }),
    )
  })

  it('builds explicit and all-filtered selection payloads with exclusions', async () => {
    const wrapper = await mountDialog({ total: 120 })
    const vm = state(wrapper)

    vm.toggleRowSelection(vm.rows[0], true)
    expect(vm.getSelectionPayload()).toEqual({ selection_mode: 'explicit', id_list: [1] })

    vm.selectAllMatchingResults()
    vm.searchValue = 'holiday'
    vm.statusFilter = 'success'
    vm.sinceDate = '2026-01-01'
    vm.beforeDate = '2026-02-01'
    vm.toggleRowSelection(vm.rows[1], false)
    expect(vm.selectedCount).toBe(119)
    expect(vm.getSelectionPayload()).toEqual({
      selection_mode: 'all_filtered',
      exclude_ids: [2],
      search_value: 'holiday',
      status: 'success',
      after: '2026-01-01',
      before: '2026-02-01',
    })
  })

  it('deletes an explicit selection without opening metadata confirmation', async () => {
    const wrapper = await mountDialog()
    const vm = state(wrapper)
    vm.toggleRowSelection(vm.rows[0], true)

    vm.deleteSelected()
    await flushPromises()

    expect(axios).toHaveBeenCalledWith({
      method: 'delete',
      url: '/api/history/tasks',
      data: { selection_mode: 'explicit', id_list: [1] },
    })
  })

  it('requires confirmation when selected history has metadata', async () => {
    const wrapper = await mountDialog({ tasks: makeTasks(1, 1, true) })
    const vm = state(wrapper)
    vm.toggleRowSelection(vm.rows[0], true)

    vm.deleteSelected()

    expect(vm.deleteDialogOpen).toBe(true)
    expect(axios).not.toHaveBeenCalledWith(expect.objectContaining({ method: 'delete' }))
  })

  it('reprocesses all filtered history into the chosen library', async () => {
    const wrapper = await mountDialog({ total: 120 })
    const vm = state(wrapper)
    vm.selectAllMatchingResults()
    vm.selectedLibraryId = 9

    vm.addSelectedToPendingTaskList()
    await flushPromises()

    expect(axios).toHaveBeenCalledWith({
      method: 'post',
      url: '/api/history/reprocess',
      data: {
        selection_mode: 'all_filtered',
        exclude_ids: [],
        search_value: '',
        status: 'all',
        after: null,
        before: null,
        library_id: 9,
      },
    })
  })

  it('loads the next page and reports completion to infinite scroll', async () => {
    const first = makeTasks(1, 50)
    const second = makeTasks(51, 1)
    axios.mockImplementation(({ url, data }) => {
      if (url === '/api/history/tasks') {
        return Promise.resolve(taskResponse(data.start === 0 ? first : second, 51))
      }
      return Promise.resolve({ data: {} })
    })
    const wrapper = mountCompletedDialog()
    await flushPromises()
    const vm = state(wrapper)
    const done = vi.fn()

    vm.loadMore(1, done)
    await flushPromises()

    expect(vm.rows).toHaveLength(51)
    expect(done).toHaveBeenCalledWith(true)
  })

  it('refreshes the loaded head while retaining the loaded tail', async () => {
    const first = makeTasks(1, 51)
    const refreshed = [{ ...makeTasks(99, 1)[0], task_label: 'Newest' }, ...makeTasks(2, 49)]
    let calls = 0
    axios.mockImplementation(({ url }) => {
      if (url === '/api/history/tasks') {
        calls += 1
        return Promise.resolve(taskResponse(calls === 1 ? first : refreshed, 51))
      }
      return Promise.resolve({ data: {} })
    })
    const wrapper = mountCompletedDialog()
    await flushPromises()
    const vm = state(wrapper)

    await vm.fetchCompletedTasks({ refreshTop: true, silent: true })

    expect(vm.rows).toHaveLength(51)
    expect(vm.rows[0].id).toBe(99)
    expect(vm.rows[50].id).toBe(51)
  })

  it('opens task details through the Quasar dialog boundary', async () => {
    const wrapper = await mountDialog()

    state(wrapper).openDetailsDialog(42)

    expect(quasar.dialog).toHaveBeenCalledWith(expect.objectContaining({ componentProps: { completedTaskId: 42 } }))
  })

  it('notifies when an action has no selection or a fetch fails', async () => {
    const wrapper = await mountDialog()
    state(wrapper).addSelectedToPendingTaskList()

    axios.mockRejectedValueOnce(new Error('offline'))
    await state(wrapper).fetchCompletedTasks({ reset: true })

    expect(quasar.notify).toHaveBeenCalledWith(expect.objectContaining({ color: 'warning' }))
    expect(quasar.notify).toHaveBeenCalledWith(expect.objectContaining({ color: 'negative' }))
  })
})
