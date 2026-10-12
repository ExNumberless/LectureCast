import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Player } from './Player'
import { fromChapters } from './timeline'
import type { PlayerLecture, Slide } from './timeline'

function lecture(slides: Slide[]): PlayerLecture {
  return {
    course: 'Calculus',
    title: 'Limits',
    audio: 'https://media.example/lecture.mp3',
    sections: slides.map((slide) => ({ n: slide.n, title: slide.title, narration: slide.narration, start_ms: slide.start_ms, end_ms: slide.end_ms, slide })),
  }
}

const base = { source: 'notes.md', locator: null }
const markdown = (n: number, text: string, start_ms: number, end_ms: number): Slide =>
  ({ ...base, n, kind: 'markdown', title: `Slide ${n}`, markdown: text, narration: `Narration ${n}`, start_ms, end_ms })

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
})

describe('Player', () => {
  it('never renders HTML from slide markdown', () => {
    const { container } = render(<Player lecture={lecture([
      markdown(1, 'Hello <script>window.pwned = true</script> <img src=x onerror="window.pwned = true"> **bold**', 0, 1000),
    ])} />)
    const slide = container.querySelector('.slide-markdown')!
    expect(slide.querySelector('script')).toBeNull()
    expect(slide.querySelector('img')).toBeNull()
    expect(container.querySelector('[onerror]')).toBeNull()
    expect(within(slide as HTMLElement).getByText('bold').tagName).toBe('STRONG')
  })

  it('renders math with KaTeX', () => {
    const { container } = render(<Player lecture={lecture([markdown(1, 'The limit $\\lim_{x \\to 0} x$', 0, 1000)])} />)
    expect(container.querySelector('.slide-markdown .katex')).not.toBeNull()
  })

  it('highlights code slides without running their contents', () => {
    const code: Slide = { ...base, n: 1, kind: 'code', title: 'Code', code: 'def f():\n    return "<b>x</b>"', language: 'python', narration: '', start_ms: 0, end_ms: 1000 }
    const { container } = render(<Player lecture={lecture([code])} />)
    const block = container.querySelector('.slide-code code')!
    expect(block.querySelector('.hljs-keyword')?.textContent).toBe('def')
    expect(block.querySelector('b')).toBeNull()
    expect(block.textContent).toContain('"<b>x</b>"')
  })

  it('starts at the deep-linked slide and moves with the keyboard and buttons', () => {
    const onIndexChange = vi.fn()
    const { container } = render(<Player
      lecture={lecture([markdown(1, 'One', 0, 1000), markdown(2, 'Two', 1000, 2000), markdown(3, 'Three', 2000, 3000)])}
      initialIndex={1}
      onIndexChange={onIndexChange}
    />)
    const audio = container.querySelector('audio')!
    expect(screen.getByText('Slide 2 of 3')).toBeInTheDocument()
    expect(audio.currentTime).toBe(1)

    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByText('Slide 3 of 3')).toBeInTheDocument()
    expect(audio.currentTime).toBe(2)
    expect(onIndexChange).toHaveBeenLastCalledWith(2)

    fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByText('Slide 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

    fireEvent.keyDown(window, { key: ' ' })
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled()
  })

  it('highlights the current slide in the narration panel', () => {
    render(<Player lecture={lecture([markdown(1, 'One', 0, 1000), markdown(2, 'Two', 1000, 2000)])} initialIndex={1} />)
    const current = within(screen.getByRole('list', { name: 'Narration' })).getAllByRole('listitem').find((item) => item.getAttribute('aria-current'))
    expect(current).toHaveTextContent('Narration 2')
  })

  it('advances or stops at slide ends as playback reaches them', () => {
    const { container } = render(<Player lecture={lecture([markdown(1, 'One', 0, 1000), markdown(2, 'Two', 1500, 2000)])} />)
    const audio = container.querySelector('audio')!

    audio.currentTime = 1.0
    fireEvent.timeUpdate(audio)
    expect(screen.getByText('Slide 2 of 2')).toBeInTheDocument()
    expect(audio.currentTime).toBe(1.5)

    fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
    fireEvent.click(screen.getByLabelText('Auto-advance'))
    audio.currentTime = 1.0
    fireEvent.timeUpdate(audio)
    expect(screen.getByText('Slide 1 of 2')).toBeInTheDocument()
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled()
  })

  it('shows chapters and narration for audio-only lectures', () => {
    render(<Player lecture={fromChapters(
      { course: 'Biology', title: 'Cells', audio: 'cells.mp3' },
      [{ n: 1, title: 'Cells', start_ms: 0, end_ms: 1000, narration: 'About cells.' }, { n: 2, title: 'Organelles', start_ms: 1000, end_ms: 2000 }],
      'https://media.example/',
    )} />)
    const chapters = screen.getByRole('list', { name: 'Chapters' })
    fireEvent.click(within(chapters).getByRole('button', { name: /Organelles/ }))
    expect(screen.getByText('Chapter 2 of 2')).toBeInTheDocument()
    expect(screen.getByText('About cells.')).toBeInTheDocument()
  })
})
