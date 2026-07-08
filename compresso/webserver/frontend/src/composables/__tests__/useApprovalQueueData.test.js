import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { useApprovalQueueData } from '../useApprovalQueueData'

vi.mock('axios', () => ({ default: { post: vi.fn() } }))

vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: vi.fn((version, endpoint) => `http://localhost/compresso/api/${version}/${endpoint}`),
}))

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const PAGE_1 = {
  page: 1,
  rowsPerPage: 25,
  rowsNumber: 0,
  sortBy: 'finish_time',
  descending: true,
}

const PAGE_2 = {
  ...PAGE_1,
  page: 2,
}

describe('useApprovalQueueData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ignores older task responses when a newer request has already won', async () => {
    const firstRequest = deferred()
    const secondRequest = deferred()
    axios.post.mockReturnValueOnce(firstRequest.promise).mockReturnValueOnce(secondRequest.promise)

    const queue = useApprovalQueueData()
    const firstFetch = queue.fetchTasks({ pagination: PAGE_1 })
    const secondFetch = queue.fetchTasks({ pagination: PAGE_2 })

    secondRequest.resolve({
      data: {
        results: [{ id: 2, abspath: '/media/newer.mkv' }],
        recordsFiltered: 1,
      },
    })
    await secondFetch

    firstRequest.resolve({
      data: {
        results: [{ id: 1, abspath: '/media/older.mkv' }],
        recordsFiltered: 1,
      },
    })
    await firstFetch

    expect(queue.tasks.value).toEqual([{ id: 2, abspath: '/media/newer.mkv' }])
    expect(queue.pagination.value.page).toBe(2)
    expect(queue.loading.value).toBe(false)
  })

  it('counts new items only for same-view refreshes', async () => {
    axios.post
      .mockResolvedValueOnce({
        data: {
          results: [{ id: 1, abspath: '/media/one.mkv' }],
          recordsFiltered: 1,
        },
      })
      .mockResolvedValueOnce({
        data: {
          results: [
            { id: 1, abspath: '/media/one.mkv' },
            { id: 2, abspath: '/media/two.mkv' },
          ],
          recordsFiltered: 2,
        },
      })
      .mockResolvedValueOnce({
        data: {
          results: [{ id: 3, abspath: '/media/filtered.mkv' }],
          recordsFiltered: 1,
        },
      })

    const queue = useApprovalQueueData()

    await queue.fetchTasks({ pagination: PAGE_1 })
    await queue.fetchTasks({ pagination: PAGE_1 })
    expect(queue.newItemCount.value).toBe(1)

    queue.searchValue.value = 'filtered'
    await queue.fetchTasks({ pagination: PAGE_1 })
    expect(queue.newItemCount.value).toBe(1)
  })
})
