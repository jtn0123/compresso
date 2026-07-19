import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('axios', () => ({ default: { post: vi.fn() } }))
vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: vi.fn((version, endpoint) => `/compresso/api/${version}/${endpoint}`),
}))
vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({ notify: vi.fn() }),
  Notify: { create: vi.fn() },
  Dialog: {},
  LocalStorage: { getItem: vi.fn(), setItem: vi.fn() },
  SessionStorage: { getItem: vi.fn(), setItem: vi.fn() },
}))

import { shallowMountWithQuasar } from 'src/test-utils'
import SelectMediaFileDialog from '../SelectMediaFileDialog.vue'

describe('SelectMediaFileDialog', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps navigation inside the selected library root', () => {
    const wrapper = shallowMountWithQuasar(SelectMediaFileDialog, {
      props: { initialPath: '/media/movies' },
    })
    wrapper.vm.rootPath = '/media/movies'
    wrapper.vm.directories = [
      { name: '..', full_path: '/media' },
      { name: 'Action', full_path: '/media/movies/Action' },
    ]

    expect(wrapper.vm.visibleDirectories).toEqual([{ name: 'Action', full_path: '/media/movies/Action' }])
  })
})
