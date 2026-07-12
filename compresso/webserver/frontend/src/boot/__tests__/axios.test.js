import { describe, expect, it } from 'vitest'

import { isInternalRequestUrl, shouldRetryApiAuth } from '../axios'

describe('Axios API authentication boundary', () => {
  it('recognizes only relative and same-origin URLs as internal', () => {
    expect(isInternalRequestUrl('/api/v2/status')).toBe(true)
    expect(isInternalRequestUrl(`${window.location.origin}/api/v2/status`)).toBe(true)
    expect(isInternalRequestUrl('//attacker.example/api')).toBe(false)
    expect(isInternalRequestUrl(`${window.location.origin}.attacker.example/api`)).toBe(false)
  })

  it('retries authentication only for same-origin 401 responses', () => {
    expect(
      shouldRetryApiAuth({
        response: { status: 401 },
        config: { url: '/api/v2/status' },
      }),
    ).toBe(true)
    expect(
      shouldRetryApiAuth({
        response: { status: 401 },
        config: { url: '//attacker.example/api' },
      }),
    ).toBe(false)
    expect(
      shouldRetryApiAuth({
        response: { status: 401 },
        config: { url: '/api/v2/status', __compressoAuthRetried: true },
      }),
    ).toBe(false)
  })
})
