import { describe, it, expect } from 'vitest'
import { bbCodeToHTML, markdownToHTML } from '../markupParser'

describe('bbCodeToHTML', () => {
  it('converts [b]text[/b] to bold HTML', () => {
    const result = bbCodeToHTML('[b]bold text[/b]')
    expect(result).toContain('xbbcode-b')
    expect(result).toContain('bold text')
  })

  it('converts [i]text[/i] to italic HTML', () => {
    const result = bbCodeToHTML('[i]italic text[/i]')
    expect(result).toContain('xbbcode-i')
    expect(result).toContain('italic text')
  })

  it('converts [url=...]...[/url] to anchor tags', () => {
    const result = bbCodeToHTML('[url=https://example.com]click here[/url]')
    expect(result).toContain('<a')
    expect(result).toContain('href=')
    expect(result).toContain('https://example.com')
    expect(result).toContain('click here')
    expect(result).toContain('</a>')
  })

  it('returns plain text unchanged', () => {
    const result = bbCodeToHTML('just plain text')
    expect(result).toContain('just plain text')
  })

  it('handles empty string', () => {
    const result = bbCodeToHTML('')
    // xbbcode-parser wraps output in a div container even for empty input
    expect(result).not.toContain('xbbcode-')
    expect(result.replace(/<[^>]*>/g, '')).toBe('')
  })

  it('handles nested tags', () => {
    const result = bbCodeToHTML('[b][i]bold and italic[/i][/b]')
    expect(result).toContain('xbbcode-b')
    expect(result).toContain('xbbcode-i')
    expect(result).toContain('bold and italic')
  })
})

describe('markdownToHTML', () => {
  it('converts **bold** to <strong>', () => {
    const result = markdownToHTML('**bold text**')
    expect(result).toContain('<strong>')
    expect(result).toContain('bold text')
    expect(result).toContain('</strong>')
  })

  it('converts *italic* to <em>', () => {
    const result = markdownToHTML('*italic text*')
    expect(result).toContain('<em>')
    expect(result).toContain('italic text')
    expect(result).toContain('</em>')
  })

  it('converts `code` to <code>', () => {
    const result = markdownToHTML('`inline code`')
    expect(result).toContain('<code>')
    expect(result).toContain('inline code')
    expect(result).toContain('</code>')
  })

  it('converts # heading to <h1>', () => {
    const result = markdownToHTML('# My Heading')
    expect(result).toContain('<h1>')
    expect(result).toContain('My Heading')
    expect(result).toContain('</h1>')
  })

  it('converts [text](url) to anchor tag', () => {
    const result = markdownToHTML('[click here](https://example.com)')
    expect(result).toContain('<a')
    expect(result).toContain('href="https://example.com"')
    expect(result).toContain('click here')
    expect(result).toContain('</a>')
  })

  it('handles empty string', () => {
    const result = markdownToHTML('')
    expect(result).toBe('')
  })

  it('wraps plain text in <p>', () => {
    const result = markdownToHTML('just plain text')
    expect(result).toContain('<p>')
    expect(result).toContain('just plain text')
    expect(result).toContain('</p>')
  })

  it('preserves raw HTML when html option is true', () => {
    const result = markdownToHTML('<div class="test">raw html</div>')
    expect(result).toContain('<div class="test">')
    expect(result).toContain('raw html')
    expect(result).toContain('</div>')
  })
})
