import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getApiToken, getWebsocketProtocols, promptForApiToken, setApiToken } from '../apiAuth'

describe('API auth session', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('keeps API credentials in tab-scoped session storage', () => {
    setApiToken('secret')

    expect(getApiToken()).toBe('secret')
    expect(localStorage.getItem('compresso-api-token')).toBeNull()
  })

  it('builds a WebSocket protocol without putting the token in the URL', () => {
    setApiToken('token with punctuation: !')

    const protocols = getWebsocketProtocols()

    expect(protocols[0]).toBe('compresso')
    expect(protocols[1]).toMatch(/^compresso-auth\.[A-Za-z0-9_-]+$/)
    expect(protocols.join(',')).not.toContain('token with punctuation')
  })

  it('stores a token entered through the authentication prompt', () => {
    vi.stubGlobal('prompt', vi.fn(() => ' entered-token '))

    expect(promptForApiToken()).toBe('entered-token')
    expect(getApiToken()).toBe('entered-token')
  })
})
