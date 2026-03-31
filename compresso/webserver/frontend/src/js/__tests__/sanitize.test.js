import { describe, it, expect } from 'vitest'
import { sanitizeHtml } from '../sanitize'

describe('sanitizeHtml', () => {
  it('returns empty string for falsy input', () => {
    expect(sanitizeHtml('')).toBe('')
    expect(sanitizeHtml(null)).toBe('')
    expect(sanitizeHtml(undefined)).toBe('')
    expect(sanitizeHtml(0)).toBe('')
  })

  it('preserves plain text', () => {
    expect(sanitizeHtml('hello world')).toBe('hello world')
  })

  it('preserves safe HTML spans with style', () => {
    const input = '<span style="color: #1a6b4a">DEBUG</span> log message'
    expect(sanitizeHtml(input)).toContain('style="color: #1a6b4a"')
  })

  it('strips script tags', () => {
    expect(sanitizeHtml('<script>alert(1)</script>hello')).toBe('hello')
  })

  it('strips onerror attributes', () => {
    expect(sanitizeHtml('<img onerror="alert(1)" src="x">')).not.toContain('onerror')
  })

  it('strips javascript: URLs', () => {
    expect(sanitizeHtml('<a href="javascript:alert(1)">click</a>')).not.toContain('javascript:')
  })

  it('preserves markdown-generated HTML', () => {
    const html = '<h2>Title</h2><p>Text <strong>bold</strong></p><img src="https://shields.io/badge" alt="badge">'
    const result = sanitizeHtml(html)
    expect(result).toContain('<h2>')
    expect(result).toContain('<strong>')
    expect(result).toContain('src="https://shields.io/badge"')
  })

  it('preserves anchor tags with target attribute', () => {
    const html = '<a href="https://example.com" target="_blank">link</a>'
    const result = sanitizeHtml(html)
    expect(result).toContain('target="_blank"')
    expect(result).toContain('href="https://example.com"')
  })

  it('preserves table elements', () => {
    const html = '<table><thead><tr><th>Header</th></tr></thead><tbody><tr><td>Cell</td></tr></tbody></table>'
    const result = sanitizeHtml(html)
    expect(result).toContain('<table>')
    expect(result).toContain('<th>')
    expect(result).toContain('<td>')
  })

  it('strips iframe tags', () => {
    expect(sanitizeHtml('<iframe src="https://evil.com"></iframe>hello')).toBe('hello')
  })

  it('strips event handler attributes on allowed tags', () => {
    expect(sanitizeHtml('<div onclick="alert(1)">text</div>')).not.toContain('onclick')
  })

  // Nested malicious HTML
  it('strips nested script tags inside allowed elements', () => {
    const input = '<div><p>safe<script>alert("xss")</script></p></div>'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('<script>')
    expect(result).not.toContain('alert')
    expect(result).toContain('safe')
  })

  it('strips deeply nested event handlers', () => {
    const input = '<div><p><span><a href="#" onmouseover="alert(1)">hover</a></span></p></div>'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('onmouseover')
    expect(result).toContain('hover')
  })

  it('strips nested iframes inside allowed tags', () => {
    const input = '<div><p>text<iframe src="https://evil.com"></iframe>more</p></div>'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('<iframe')
    expect(result).toContain('text')
    expect(result).toContain('more')
  })

  // SVG-based XSS
  it('strips SVG elements with embedded scripts', () => {
    const input = '<svg onload="alert(1)"><circle r="10"/></svg>'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('<svg')
    expect(result).not.toContain('onload')
  })

  it('strips SVG use elements referencing external resources', () => {
    const input = '<svg><use href="https://evil.com/payload#x"></use></svg>'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('<svg')
    expect(result).not.toContain('<use')
  })

  it('strips SVG foreignObject with embedded HTML attack', () => {
    const input = '<svg><foreignObject><body onload="alert(1)"><p>xss</p></body></foreignObject></svg>'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('foreignObject')
    expect(result).not.toContain('onload')
  })

  // data: URL stripping
  it('strips data: URLs in anchor href', () => {
    const input = '<a href="data:text/html,<script>alert(1)</script>">click</a>'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('data:text/html')
  })

  it('strips data: URLs in img src', () => {
    const input = '<img src="data:text/html,<script>alert(1)</script>">'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('data:text/html')
  })

  it('strips data: URLs with base64 encoding', () => {
    const input = '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">click</a>'
    const result = sanitizeHtml(input)
    expect(result).not.toContain('data:text/html;base64')
  })
})
