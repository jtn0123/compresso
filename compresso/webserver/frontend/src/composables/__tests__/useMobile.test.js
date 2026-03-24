import { describe, it, expect, vi } from 'vitest'

// Mock quasar before importing
const mockScreen = { lt: { md: false } }
const mockPlatform = { is: { mobile: false } }

vi.mock('quasar', () => ({
  useQuasar: () => ({
    screen: mockScreen,
    platform: mockPlatform,
  }),
}))

import { useMobile } from '../useMobile'

describe('useMobile', () => {
  it('returns an object with isMobile computed ref', () => {
    const { isMobile } = useMobile()
    expect(isMobile).toBeDefined()
    expect(isMobile.value).toBe(false)
  })

  it('returns true when screen is smaller than md breakpoint', () => {
    mockScreen.lt.md = true
    mockPlatform.is.mobile = false

    const { isMobile } = useMobile()
    expect(isMobile.value).toBe(true)

    mockScreen.lt.md = false
  })

  it('returns true when platform is mobile', () => {
    mockScreen.lt.md = false
    mockPlatform.is.mobile = true

    const { isMobile } = useMobile()
    expect(isMobile.value).toBe(true)

    mockPlatform.is.mobile = false
  })

  it('returns true when both screen is small and platform is mobile', () => {
    mockScreen.lt.md = true
    mockPlatform.is.mobile = true

    const { isMobile } = useMobile()
    expect(isMobile.value).toBe(true)

    mockScreen.lt.md = false
    mockPlatform.is.mobile = false
  })

  it('returns false when screen is large and platform is not mobile', () => {
    mockScreen.lt.md = false
    mockPlatform.is.mobile = false

    const { isMobile } = useMobile()
    expect(isMobile.value).toBe(false)
  })
})
