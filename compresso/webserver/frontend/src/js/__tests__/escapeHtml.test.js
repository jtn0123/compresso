import { describe, it, expect } from 'vitest'
import { escapeHtml } from '../compressoWebsocket'

describe('escapeHtml', () => {
  it('returns empty string for null', () => {
    expect(escapeHtml(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(escapeHtml(undefined)).toBe('')
  })

  it('returns empty string for empty string', () => {
    expect(escapeHtml('')).toBe('')
  })

  it('leaves safe strings unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world')
  })

  it('escapes ampersands', () => {
    expect(escapeHtml('a&b')).toBe('a&amp;b')
  })

  it('escapes angle brackets', () => {
    expect(escapeHtml('<div>')).toBe('&lt;div&gt;')
  })

  it('escapes double quotes', () => {
    expect(escapeHtml('say "hello"')).toBe('say &quot;hello&quot;')
  })

  it('escapes single quotes', () => {
    expect(escapeHtml("it's")).toBe("it&#039;s")
  })

  it('escapes all special characters together', () => {
    expect(escapeHtml('<a href="test">&</a>')).toBe(
      '&lt;a href=&quot;test&quot;&gt;&amp;&lt;/a&gt;'
    )
  })

  it('neutralizes a script injection payload', () => {
    const payload = '<script>alert("xss")</script>'
    const result = escapeHtml(payload)
    expect(result).not.toContain('<script>')
    expect(result).toBe('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;')
  })
})
