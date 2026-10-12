import type { PlayerJson } from '../contracts/player.types'

export type Slide = PlayerJson['slides'][number]

/** One narrated section: a slide with its audio chapter, or just the chapter for audio-only lectures. */
export type Section = {
  n: number
  title: string
  narration: string
  start_ms: number
  end_ms: number
  slide: Slide | null
}

export type PlayerLecture = {
  course: string
  title: string
  audio: string
  sections: Section[]
}

/** A chapter from `<name>.chapters.json`, with the narration text when it is known. */
export type Chapter = { n: number; title: string; start_ms: number; end_ms: number; narration?: string }

/** Resolve a path relative to the file it came from, as player.json paths are. */
export function resolveAsset(path: string, base: string) {
  return new URL(path, new URL(base, window.location.href)).href
}

export function fromPlayerJson(json: PlayerJson, base: string): PlayerLecture {
  return {
    course: json.course,
    title: json.title,
    audio: resolveAsset(json.audio, base),
    sections: json.slides.map((slide) => ({
      n: slide.n,
      title: slide.title,
      narration: slide.narration,
      start_ms: slide.start_ms,
      end_ms: slide.end_ms,
      slide: slide.kind === 'image' ? { ...slide, image: resolveAsset(slide.image, base) } : slide,
    })),
  }
}

/** An audio-only lecture: chapters and narration in place of slides. */
export function fromChapters(
  lecture: { course: string; title: string; audio: string },
  chapters: Chapter[],
  base: string,
): PlayerLecture {
  return {
    course: lecture.course,
    title: lecture.title,
    audio: resolveAsset(lecture.audio, base),
    sections: chapters.map((chapter) => ({ ...chapter, narration: chapter.narration ?? '', slide: null })),
  }
}

/** The section playing at `ms`: the last one that has started, or the first before any has. */
export function sectionIndexAt(sections: Section[], ms: number) {
  let index = 0
  for (let i = 0; i < sections.length; i++) {
    if (sections[i].start_ms <= ms) index = i
    else break
  }
  return index
}

export type TickResult =
  | { action: 'continue'; index: number }
  | { action: 'seek'; index: number; ms: number }
  | { action: 'pause'; index: number; ms: number }

/**
 * Decide what happens when playback reaches `ms` while section `current` is showing.
 * Auto-advance moves on at the section's end (seeking over any gap to the next start);
 * without it, playback stops at the end of the current section.
 */
export function tick(sections: Section[], current: number, ms: number, autoAdvance: boolean): TickResult {
  const section = sections[current]
  if (!section) return { action: 'continue', index: sectionIndexAt(sections, ms) }
  if (ms < section.start_ms) return { action: 'continue', index: sectionIndexAt(sections, ms) }
  if (ms < section.end_ms) return { action: 'continue', index: current }

  const next = current + 1
  if (!autoAdvance || next >= sections.length) return { action: 'pause', index: current, ms: section.end_ms }
  if (ms < sections[next].start_ms) return { action: 'seek', index: next, ms: sections[next].start_ms }
  return { action: 'continue', index: sectionIndexAt(sections, ms) }
}

export function clampIndex(sections: Section[], index: number) {
  return Math.min(Math.max(index, 0), Math.max(sections.length - 1, 0))
}
