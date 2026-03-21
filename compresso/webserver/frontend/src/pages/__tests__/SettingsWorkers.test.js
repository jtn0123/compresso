import { describe, it, expect } from 'vitest'
import { checkUnsavedChanges } from '../../js/settingsUtils'

describe('checkUnsavedChanges', () => {
  it('returns false when originalCachePath is null', () => {
    expect(checkUnsavedChanges(null, '/some/path')).toBe(false)
  })

  it('returns false when cachePath equals originalCachePath', () => {
    expect(checkUnsavedChanges('/cache/path', '/cache/path')).toBe(false)
  })

  it('returns true when cachePath differs from originalCachePath', () => {
    expect(checkUnsavedChanges('/cache/path', '/new/cache/path')).toBe(true)
  })

  it('returns false when both are empty strings', () => {
    expect(checkUnsavedChanges('', '')).toBe(false)
  })

  it('returns true when originalCachePath is empty but cachePath is set', () => {
    expect(checkUnsavedChanges('', '/new/path')).toBe(true)
  })
})
