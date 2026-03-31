import DOMPurify from 'dompurify'

/**
 * Sanitize HTML content to prevent XSS attacks.
 * Preserves safe HTML tags (spans, p, img, etc.) and inline styles
 * used for log coloring and markdown rendering.
 */
export function sanitizeHtml(dirty) {
  if (!dirty) return ''
  return DOMPurify.sanitize(dirty, {
    ADD_ATTR: ['style', 'target'],
    ALLOWED_TAGS: [
      'span',
      'p',
      'div',
      'br',
      'hr',
      'pre',
      'code',
      'b',
      'i',
      'em',
      'strong',
      'u',
      's',
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'h6',
      'ul',
      'ol',
      'li',
      'a',
      'img',
      'table',
      'thead',
      'tbody',
      'tr',
      'th',
      'td',
      'blockquote',
    ],
  })
}
