import { describe, expect, it } from 'vitest'

import { diffLines } from './diff'

describe('diffLines', () => {
  it('marks only the changed lines', () => {
    expect(diffLines('a\nb\nc', 'a\nB\nc\nd')).toEqual([
      { kind: 'same', text: 'a' },
      { kind: 'removed', text: 'b' },
      { kind: 'added', text: 'B' },
      { kind: 'same', text: 'c' },
      { kind: 'added', text: 'd' },
    ])
  })

  it('reports no changes for identical text', () => {
    expect(diffLines('x\ny', 'x\ny').every((line) => line.kind === 'same')).toBe(true)
  })
})
