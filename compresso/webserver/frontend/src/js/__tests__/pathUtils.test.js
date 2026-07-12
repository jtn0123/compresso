import { describe, expect, it } from 'vitest'
import { displayBasename } from '../pathUtils'

describe('displayBasename', () => {
  it.each([
    ['/media/movies/file.mkv', 'file.mkv'],
    ['C:\\Media\\Movies\\file.mkv', 'file.mkv'],
    ['mixed/path\\file.mkv', 'file.mkv'],
    ['', ''],
    [null, ''],
  ])('extracts a display name from %s', (path, expected) => {
    expect(displayBasename(path)).toBe(expected)
  })
})
