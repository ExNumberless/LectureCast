import { describe, expect, it } from 'vitest'

import fixture from '../contracts/player.json'
import type { PlayerJson } from '../contracts/player.types'
import { clampIndex, fromChapters, fromPlayerJson, sectionIndexAt, tick } from './timeline'
import type { Section } from './timeline'

const section = (n: number, start_ms: number, end_ms: number): Section =>
  ({ n, title: `S${n}`, narration: '', start_ms, end_ms, slide: null })

// A gap between the second and third sections, as when chapters are trimmed.
const sections = [section(1, 0, 1000), section(2, 1000, 2000), section(3, 2500, 4000)]

describe('sectionIndexAt', () => {
  it('finds the section that has most recently started', () => {
    expect(sectionIndexAt(sections, 0)).toBe(0)
    expect(sectionIndexAt(sections, 999)).toBe(0)
    expect(sectionIndexAt(sections, 1000)).toBe(1)
    expect(sectionIndexAt(sections, 2200)).toBe(1)
    expect(sectionIndexAt(sections, 9000)).toBe(2)
  })
})

describe('tick', () => {
  it('keeps the current section while it plays', () => {
    expect(tick(sections, 0, 500, true)).toEqual({ action: 'continue', index: 0 })
  })

  it('advances into a contiguous next section', () => {
    expect(tick(sections, 0, 1000, true)).toEqual({ action: 'continue', index: 1 })
  })

  it('seeks over a gap to the next section when auto-advancing', () => {
    expect(tick(sections, 1, 2000, true)).toEqual({ action: 'seek', index: 2, ms: 2500 })
  })

  it('pauses at the end of the section without auto-advance', () => {
    expect(tick(sections, 0, 1010, false)).toEqual({ action: 'pause', index: 0, ms: 1000 })
  })

  it('pauses at the end of the last section', () => {
    expect(tick(sections, 2, 4000, true)).toEqual({ action: 'pause', index: 2, ms: 4000 })
  })

  it('follows a seek backwards', () => {
    expect(tick(sections, 2, 1500, false)).toEqual({ action: 'continue', index: 1 })
  })
})

describe('lectures', () => {
  it('resolves player.json paths against its own location', () => {
    const lecture = fromPlayerJson(fixture as PlayerJson, 'https://media.example/c/1/slides/lecture-01/player.json')
    expect(lecture.audio).toBe('https://media.example/c/1/audio/lecture-01.mp3')
    const image = lecture.sections[1].slide
    expect(image?.kind === 'image' && image.image).toBe('https://media.example/c/1/slides/lecture-01/7.webp')
    expect(lecture.sections.map((item) => [item.n, item.start_ms, item.end_ms])).toEqual([[5, 0, 3600], [7, 3600, 5800]])
  })

  it('builds audio-only lectures from chapters', () => {
    const lecture = fromChapters(
      { course: 'Biology', title: 'Cells', audio: 'lecture-01.mp3' },
      [{ n: 5, title: 'Cells', start_ms: 0, end_ms: 3600 }],
      'https://media.example/audio/',
    )
    expect(lecture.sections).toEqual([{ n: 5, title: 'Cells', narration: '', start_ms: 0, end_ms: 3600, slide: null }])
  })

  it('clamps slide indexes', () => {
    expect(clampIndex(sections, -1)).toBe(0)
    expect(clampIndex(sections, 7)).toBe(2)
  })
})
