import DOMPurify from 'dompurify'
import { marked } from 'marked'

/** Render manager-authored contest Markdown as safe HTML for the public page. */
export function renderContestMarkdown(source: string | null): string {
  if (!source?.trim()) return ''
  const html = marked.parse(source, { async: false })
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'a',
      'blockquote',
      'br',
      'code',
      'del',
      'em',
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'h6',
      'hr',
      'li',
      'ol',
      'p',
      'pre',
      'strong',
      'table',
      'tbody',
      'td',
      'th',
      'thead',
      'tr',
      'ul',
    ],
    ALLOWED_ATTR: ['align', 'href', 'title'],
    SANITIZE_NAMED_PROPS: true,
  })
}
