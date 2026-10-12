import { describe, expect, it } from 'vitest'

import fixture from './player.json'
import { isPlayerJson } from './player'
import type { PlayerJson } from './player.types'

describe('player.json contract', () => {
  it('validates the fixture using both library schemas', () => {
    expect(isPlayerJson(fixture)).toBe(true)
  })

  it('rejects slides with fields outside the schema', () => {
    const invalid = {
      ...fixture,
      slides: [{ ...fixture.slides[0], extra: true }],
    }
    expect(isPlayerJson(invalid)).toBe(false)
  })

  it('generates a discriminated TypeScript union for the three slide kinds', () => {
    const slides: PlayerJson['slides'] = [
      {
        n: 5,
        kind: 'markdown',
        title: 'Cells',
        source: 'lecture-01.md',
        locator: 'section 1',
        markdown: 'Cells are the basic unit of life.',
        narration: 'Cells are the basic unit of life.',
        start_ms: 0,
        end_ms: 3600,
      },
      {
        n: 7,
        kind: 'image',
        title: 'Organelles',
        source: 'lecture-01.pdf',
        locator: 'page 2',
        image: '7.webp',
        width: 1240,
        height: 1755,
        narration: 'Organelles perform specialized functions.',
        start_ms: 3600,
        end_ms: 5800,
      },
    ]
    expect(slides.map((slide) => slide.kind)).toEqual(['markdown', 'image'])
  })
})
