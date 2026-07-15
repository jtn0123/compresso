import { describe, expect, it, vi } from 'vitest'
import { useTaskListController } from '../useTaskListController'

const rows = (start, count) => Array.from({ length: count }, (_, index) => ({ id: start + index }))

function makeController(overrides = {}) {
  const fetchPage = overrides.fetchPage || vi.fn().mockResolvedValue({ rows: rows(1, 2), total: 2 })
  const onFetchError = vi.fn()
  return {
    fetchPage,
    onFetchError,
    controller: useTaskListController({
      fetchPage,
      onFetchError,
      buildFiltersPayload: () => ({ search_value: 'movie' }),
      pageSize: 2,
    }),
  }
}

describe('useTaskListController', () => {
  it('loads, appends, and refreshes pages while preserving the loaded tail', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({ rows: rows(1, 2), total: 3 })
      .mockResolvedValueOnce({ rows: rows(3, 1), total: 3 })
      .mockResolvedValueOnce({ rows: [{ id: 9 }, { id: 1 }], total: 3 })
    const { controller } = makeController({ fetchPage })

    await controller.fetchTasks({ reset: true })
    await controller.fetchTasks()
    await controller.fetchTasks({ refreshTop: true, silent: true })

    expect(fetchPage.mock.calls.map(([request]) => request.start)).toEqual([0, 2, 0])
    expect(controller.rows.value).toEqual([{ id: 9 }, { id: 1 }, { id: 2 }])
    expect(controller.offset.value).toBe(3)
    expect(controller.allLoaded.value).toBe(true)
  })

  it('trims rows when a refresh reports a smaller total', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({ rows: rows(1, 3), total: 3 })
      .mockResolvedValueOnce({ rows: [{ id: 8 }], total: 1 })
    const { controller } = makeController({ fetchPage })

    await controller.fetchTasks({ reset: true })
    await controller.fetchTasks({ refreshTop: true })

    expect(controller.rows.value).toEqual([{ id: 8 }])
    expect(controller.offset.value).toBe(1)
  })

  it('handles explicit, page, and all-filtered selection modes', async () => {
    const { controller } = makeController()
    await controller.fetchTasks({ reset: true })

    controller.toggleRowSelection({ id: 1 }, true)
    controller.toggleRowSelection({ id: 1 }, true)
    expect(controller.getSelectionPayload()).toEqual({ selection_mode: 'explicit', id_list: [1] })

    controller.toggleSelectPage(true)
    expect(controller.allPageSelected.value).toBe(true)

    controller.totalCount.value = 5
    expect(controller.showSelectAllMatchingPrompt.value).toBe(true)
    controller.selectAllMatchingResults()
    controller.toggleRowSelection({ id: 2 }, false)
    controller.toggleRowSelection({ id: 2 }, false)
    expect(controller.selectedCount.value).toBe(4)
    expect(controller.getSelectionPayload()).toEqual({
      selection_mode: 'all_filtered',
      exclude_ids: [2],
      search_value: 'movie',
    })

    controller.toggleRowSelection({ id: 2 }, true)
    controller.toggleSelectPage(false)
    expect(controller.selectedCount.value).toBe(0)
  })

  it('records failures, invokes the error hook, and always clears loading flags', async () => {
    const failure = new Error('offline')
    const { controller, onFetchError } = makeController({ fetchPage: vi.fn().mockRejectedValue(failure) })

    await expect(controller.fetchTasks({ reset: true })).resolves.toBe(false)

    expect(controller.error.value).toBe(failure)
    expect(controller.loading.value).toBe(false)
    expect(controller.loadingMore.value).toBe(false)
    expect(onFetchError).toHaveBeenCalledWith(failure)
  })

  it('finishes infinite scrolling immediately when busy or complete', () => {
    const fetchPage = vi.fn().mockResolvedValue({ rows: rows(1, 2), total: 4 })
    const { controller } = makeController({
      fetchPage,
    })
    const done = vi.fn()

    controller.loadMore(1, done)
    expect(done).toHaveBeenCalledWith(true)

    controller.totalCount.value = 4
    controller.loading.value = true
    controller.loadMore(2, done)
    expect(done).toHaveBeenLastCalledWith(false)
    expect(fetchPage).not.toHaveBeenCalled()

    controller.loading.value = false
    controller.loadingMore.value = true
    controller.loadMore(3, done)
    expect(done).toHaveBeenLastCalledWith(false)
    expect(fetchPage).not.toHaveBeenCalled()
  })
})
