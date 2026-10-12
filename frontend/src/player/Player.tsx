import { useCallback, useEffect, useRef, useState } from 'react'

import { SlideView } from './SlideView'
import { clampIndex, sectionIndexAt, tick } from './timeline'
import type { PlayerLecture } from './timeline'

const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2]

function formatTime(ms: number) {
  const seconds = Math.floor(ms / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function isTyping(target: EventTarget | null) {
  return target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))
}

export function Player({
  lecture,
  initialIndex = 0,
  onIndexChange,
}: {
  lecture: PlayerLecture
  initialIndex?: number
  onIndexChange?: (index: number) => void
}) {
  const { sections } = lecture
  const audioRef = useRef<HTMLAudioElement>(null)
  const [index, setIndex] = useState(() => clampIndex(sections, initialIndex))
  const [positionMs, setPositionMs] = useState(sections[clampIndex(sections, initialIndex)]?.start_ms ?? 0)
  const [playing, setPlaying] = useState(false)
  const [autoAdvance, setAutoAdvance] = useState(true)
  const [speed, setSpeed] = useState(1)
  const section = sections[index]
  const durationMs = sections.at(-1)?.end_ms ?? 0
  const audioOnly = sections.every((item) => item.slide === null)

  const show = useCallback((next: number) => {
    setIndex(next)
    onIndexChange?.(next)
  }, [onIndexChange])

  const seek = useCallback((ms: number) => {
    const audio = audioRef.current
    if (audio) audio.currentTime = ms / 1000
    setPositionMs(ms)
  }, [])

  const goTo = useCallback((target: number) => {
    const next = clampIndex(sections, target)
    if (!sections[next]) return
    show(next)
    seek(sections[next].start_ms)
  }, [sections, seek, show])

  // Start at the deep-linked slide once the audio can seek.
  useEffect(() => {
    const audio = audioRef.current
    const start = sections[clampIndex(sections, initialIndex)]?.start_ms ?? 0
    if (audio && start > 0) audio.currentTime = start / 1000
  }, [initialIndex, sections])

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = speed
  }, [speed])

  function onTimeUpdate() {
    const audio = audioRef.current
    if (!audio || audio.seeking) return
    const ms = Math.round(audio.currentTime * 1000)
    setPositionMs(ms)
    const result = tick(sections, index, ms, autoAdvance)
    if (result.index !== index) show(result.index)
    if (result.action === 'seek') seek(result.ms)
    if (result.action === 'pause') audio.pause()
  }

  function onSeeked() {
    const audio = audioRef.current
    if (!audio) return
    const ms = Math.round(audio.currentTime * 1000)
    setPositionMs(ms)
    const next = sectionIndexAt(sections, ms)
    if (next !== index) show(next)
  }

  const togglePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (!audio.paused) {
      audio.pause()
      return
    }
    // Stopped at a section's end without auto-advance: play continues with the next section.
    const current = sections[index]
    if (current && audio.currentTime * 1000 >= current.end_ms && index + 1 < sections.length) goTo(index + 1)
    void audio.play()?.catch(() => setPlaying(false))
  }, [goTo, index, sections])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || isTyping(event.target)) return
      if (event.key === 'ArrowRight') goTo(index + 1)
      else if (event.key === 'ArrowLeft') goTo(index - 1)
      else if (event.key === ' ') {
        // Space on a focused button would also click it.
        if (event.target instanceof HTMLButtonElement) return
        togglePlay()
      } else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [goTo, index, togglePlay])

  if (!section) return <p role="status">This lecture has no sections to play.</p>

  return <section className="player" aria-label={`${lecture.course}: ${lecture.title}`}>
    <header className="player-header">
      <p className="eyebrow">{lecture.course}</p>
      <h1>{lecture.title}</h1>
    </header>

    <div className="player-stage">
      {section.slide
        ? <SlideView slide={section.slide} />
        : <ol className="chapter-list" aria-label="Chapters">{sections.map((item, i) => <li key={item.n}>
          <button type="button" aria-current={i === index ? 'true' : undefined} onClick={() => goTo(i)}>
            <span>{item.title}</span> <span className="chapter-time">{formatTime(item.start_ms)}</span>
          </button>
        </li>)}</ol>}
    </div>

    <audio
      ref={audioRef}
      src={lecture.audio}
      preload="metadata"
      onTimeUpdate={onTimeUpdate}
      onSeeked={onSeeked}
      onPlay={() => setPlaying(true)}
      onPause={() => setPlaying(false)}
      onEnded={() => setPlaying(false)}
    />

    <div className="player-progress">
      <input
        type="range"
        aria-label="Position"
        min={0}
        max={durationMs}
        step={100}
        value={Math.min(positionMs, durationMs)}
        onChange={(event) => seek(Number(event.target.value))}
      />
      <div className="slide-markers" aria-hidden="true">
        {sections.map((item, i) => <span
          key={item.n}
          className={i === index ? 'marker current' : 'marker'}
          style={{ left: `${durationMs ? (item.start_ms / durationMs) * 100 : 0}%` }}
        />)}
      </div>
      <span className="player-time">{formatTime(positionMs)} / {formatTime(durationMs)}</span>
    </div>

    <div className="player-controls">
      <button type="button" onClick={() => goTo(index - 1)} disabled={index === 0}>Previous</button>
      <button type="button" onClick={togglePlay}>{playing ? 'Pause' : 'Play'}</button>
      <button type="button" onClick={() => goTo(index + 1)} disabled={index >= sections.length - 1}>Next</button>
      <span className="player-count">{audioOnly ? 'Chapter' : 'Slide'} {index + 1} of {sections.length}</span>
      <label><input type="checkbox" checked={autoAdvance} onChange={(event) => setAutoAdvance(event.target.checked)} /> Auto-advance</label>
      <label>Speed <select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
        {SPEEDS.map((value) => <option key={value} value={value}>{value}×</option>)}
      </select></label>
    </div>

    <ol className="narration" aria-label="Narration">
      {sections.map((item, i) => <li key={item.n} aria-current={i === index ? 'true' : undefined}>
        <button type="button" className="narration-title" onClick={() => goTo(i)}>{item.title}</button>
        <p>{item.narration}</p>
      </li>)}
    </ol>
  </section>
}
