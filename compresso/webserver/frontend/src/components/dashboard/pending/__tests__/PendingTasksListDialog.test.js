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
import axios from 'axios'
import { shallowMountWithQuasar } from 'src/test-utils'
import PendingTasksListDialog from '../PendingTasksListDialog.vue'

const slotStub = { template: '<div><slot /></div>' }
const taskShellStub = {
  props: ['rows'],
  template: '<div><slot v-for="row in rows" name="body" :row="row" /></div>',
}
const mountPendingDialog = () =>
  shallowMountWithQuasar(PendingTasksListDialog, {
    global: {
      stubs: {
        CompressoDialogWindow: slotStub,
        CompressoStandardButtonDropdown: slotStub,
        TaskListTableShell: taskShellStub,
        'q-slide-transition': slotStub,
      },
    },
  })

const makeTasks = (start, count) =>
  Array.from({ length: count }, (_, index) => ({
    id: start + index,
    abspath: `/media/file-${start + index}.mkv`,
    library_name: 'Movies',
  }))

const libraries = {
  data: { libraries: [{ id: 7, name: 'Movies' }] },
}

const taskResponse = (results, total = results.length) => ({
  data: { results, recordsFiltered: total },
})

function state(wrapper) {
  return wrapper.vm.$.setupState
}

async function mountDialog({ tasks = makeTasks(1, 2), total = tasks.length } = {}) {
  axios.mockImplementation(({ method, url }) => {
    if (method === 'get' && url === '/api/settings/libraries') return Promise.resolve(libraries)
    if (method === 'post' && url === '/api/pending/tasks') return Promise.resolve(taskResponse(tasks, total))
    return Promise.resolve({ data: {} })
  })
  const wrapper = mountPendingDialog()
  await flushPromises()
  return wrapper
}

describe('PendingTasksListDialog interactions', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads libraries and the first pending-task page', async () => {
    const wrapper = await mountDialog()
    const vm = state(wrapper)

    expect(vm.rows).toEqual([
      { id: 1, name: '/media/file-1.mkv', libraryName: 'Movies' },
      { id: 2, name: '/media/file-2.mkv', libraryName: 'Movies' },
    ])
    expect(vm.libraryOptions).toEqual([{ label: 'Movies', value: 7 }])
    expect(vm.loading).toBe(false)
  })

  it('builds explicit and all-filtered selection payloads with exclusions', async () => {
    const wrapper = await mountDialog({ total: 80 })
    const vm = state(wrapper)

    vm.toggleSelectPage(true)
    expect(vm.getSelectionPayload()).toEqual({ selection_mode: 'explicit', id_list: [1, 2] })

    vm.searchValue = 'concert'
    vm.libraryFilters = [7]
    await flushPromises()
    vm.selectAllMatchingResults()
    vm.toggleRowSelection(vm.rows[0], false)
    expect(vm.selectedCount).toBe(79)
    expect(vm.getSelectionPayload()).toEqual({
      selection_mode: 'all_filtered',
      exclude_ids: [1],
      search_value: 'concert',
      library_ids: [7],
    })
  })

  it('clears selection when the page checkbox is unchecked', async () => {
    const wrapper = await mountDialog()
    const vm = state(wrapper)

    vm.toggleSelectPage(true)
    vm.selectAllMatchingResults()
    vm.toggleSelectPage(false)

    expect(vm.selectedIds).toEqual([])
    expect(vm.excludedIds).toEqual([])
    expect(vm.selectAllMatching).toBe(false)
  })

  it('sends the selected tasks to the reorder endpoint', async () => {
    const wrapper = await mountDialog()
    const vm = state(wrapper)
    vm.toggleRowSelection(vm.rows[0], true)

    vm.moveToTop()
    await flushPromises()

    expect(axios).toHaveBeenCalledWith({
      method: 'post',
      url: '/api/pending/reorder',
      data: { position: 'top', selection_mode: 'explicit', id_list: [1] },
    })
  })

  it('sends all-filtered deletion without expanding every task id', async () => {
    const wrapper = await mountDialog({ total: 80 })
    const vm = state(wrapper)
    vm.selectAllMatchingResults()
    vm.toggleRowSelection(vm.rows[1], false)

    vm.deleteSelected()
    await flushPromises()

    expect(axios).toHaveBeenCalledWith({
      method: 'delete',
      url: '/api/pending/tasks',
      data: {
        selection_mode: 'all_filtered',
        exclude_ids: [2],
        search_value: '',
        library_ids: [],
      },
    })
  })

  it('loads the next page and reports completion to infinite scroll', async () => {
    const first = makeTasks(1, 50)
    const second = makeTasks(51, 1)
    axios.mockImplementation(({ method, url, data }) => {
      if (method === 'get') return Promise.resolve(libraries)
      if (url === '/api/pending/tasks') {
        return Promise.resolve(taskResponse(data.start === 0 ? first : second, 51))
      }
      return Promise.resolve({ data: {} })
    })
    const wrapper = mountPendingDialog()
    await flushPromises()
    const vm = state(wrapper)
    const done = vi.fn()

    vm.loadMore(1, done)
    await flushPromises()

    expect(vm.rows).toHaveLength(51)
    expect(vm.rows[50].id).toBe(51)
    expect(done).toHaveBeenCalledWith(true)
  })

  it('refreshes the loaded head without discarding the loaded tail', async () => {
    const first = makeTasks(1, 51)
    const refreshed = [{ id: 99, abspath: '/media/new.mkv', library_name: 'Movies' }, ...makeTasks(1, 49)]
    let taskCalls = 0
    axios.mockImplementation(({ method, url }) => {
      if (method === 'get') return Promise.resolve(libraries)
      if (url === '/api/pending/tasks') {
        taskCalls += 1
        return Promise.resolve(taskResponse(taskCalls === 1 ? first : refreshed, taskCalls === 1 ? 51 : 52))
      }
      return Promise.resolve({ data: {} })
    })
    const wrapper = mountPendingDialog()
    await flushPromises()
    const vm = state(wrapper)

    await vm.fetchPendingTasks({ refreshTop: true, silent: true })

    expect(vm.rows).toHaveLength(52)
    expect(vm.rows[0].id).toBe(99)
    expect(vm.rows[51].id).toBe(51)
  })

  it('notifies instead of mutating when an action has no selection', async () => {
    const wrapper = await mountDialog()
    const vm = state(wrapper)

    vm.moveToBottom()
    vm.deleteSelected()

    expect(quasar.notify).toHaveBeenCalledTimes(2)
    expect(axios).not.toHaveBeenCalledWith(expect.objectContaining({ url: '/api/pending/reorder' }))
  })

  it('reports fetch errors and leaves the loading state', async () => {
    axios.mockImplementation(({ method }) => {
      if (method === 'get') return Promise.resolve(libraries)
      return Promise.reject(new Error('offline'))
    })

    const wrapper = mountPendingDialog()
    await flushPromises()

    expect(state(wrapper).loading).toBe(false)
    expect(quasar.notify).toHaveBeenCalledWith(expect.objectContaining({ color: 'negative' }))
  })
})
