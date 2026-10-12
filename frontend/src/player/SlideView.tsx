import hljs from 'highlight.js/lib/common'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkMath from 'remark-math'
import 'highlight.js/styles/github.css'
import 'katex/dist/katex.min.css'

import type { Slide } from './timeline'

/**
 * Slide text comes from scraped course sites, so raw HTML is never rendered (no rehype-raw):
 * only KaTeX and the code highlighter produce markup.
 */
export function MarkdownSlide({ markdown }: { markdown: string }) {
  return <div className="slide-markdown">
    <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]} skipHtml>{markdown}</ReactMarkdown>
  </div>
}

function highlightCode(code: string, language: string) {
  // highlight.js escapes the source text; its output contains only its own <span> markup.
  if (hljs.getLanguage(language)) return hljs.highlight(code, { language, ignoreIllegals: true }).value
  return hljs.highlight(code, { language: 'plaintext' }).value
}

export function CodeSlide({ code, language }: { code: string; language: string }) {
  return <pre className="slide-code"><code
    className={`hljs language-${language}`}
    dangerouslySetInnerHTML={{ __html: highlightCode(code, language) }}
  /></pre>
}

export function SlideView({ slide }: { slide: Slide }) {
  return <figure className="slide" aria-label={`Slide ${slide.n}: ${slide.title}`}>
    {slide.kind === 'image' && <img src={slide.image} width={slide.width} height={slide.height} alt={slide.title} />}
    {slide.kind === 'markdown' && <MarkdownSlide markdown={slide.markdown} />}
    {slide.kind === 'code' && <CodeSlide code={slide.code} language={slide.language} />}
  </figure>
}
