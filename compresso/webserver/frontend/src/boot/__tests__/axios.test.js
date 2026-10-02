import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('src/js/sharedLinksStore', () => ({
  sharedLinksStore: { target: 'local' },
}))

import { applyCompressoRequestHeaders } from '../axios'
import { sharedLinksStore } from 'src/js/sharedLinksStore'

describe('Compresso Axios request headers', () => {
  beforeEach(() => {
    sharedLinksStore.target = 'local'
    document.cookie = 'compresso_csrf_token=; Max-Age=0; path=/'
  })

  it('echoes the CSRF cookie for same-origin mutations', () => {
    document.cookie = 'compresso_csrf_token=csrf-value; path=/'

    const config = applyCompressoRequestHeaders({
      method: 'post',
      url: '/compresso/api/v2/approval/approve',
      headers: {},
    })

    expect(config.headers['X-Compresso-CSRF-Token']).toBe('csrf-value')
  })

  it('does not attach a CSRF header to read-only requests', () => {
    document.cookie = 'compresso_csrf_token=csrf-value; path=/'

    const config = applyCompressoRequestHeaders({
      method: 'get',
      url: '/compresso/api/v2/settings/read',
      headers: {},
    })

    expect(config.headers['X-Compresso-CSRF-Token']).toBeUndefined()
  })

  it('does not leak internal headers to an external origin', () => {
    document.cookie = 'compresso_csrf_token=csrf-value; path=/'
    sharedLinksStore.target = 'remote-node'

    const config = applyCompressoRequestHeaders({
      method: 'post',
      url: 'https://example.com/upload',
      headers: {},
    })

    expect(config.headers['X-Compresso-CSRF-Token']).toBeUndefined()
    expect(config.headers['X-Compresso-Target-Installation']).toBeUndefined()
  })

  it('keeps the existing remote-target header on internal requests', () => {
    sharedLinksStore.target = 'remote-node'

    const config = applyCompressoRequestHeaders({
      method: 'get',
      url: '/compresso/api/v2/system/status',
      headers: {},
    })

    expect(config.headers['X-Compresso-Target-Installation']).toBe('remote-node')
  })
})
