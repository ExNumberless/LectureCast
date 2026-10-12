import { useCallback } from 'react'
import { useNavigate, useParams } from 'react-router'

import { Player } from './Player'
import { loadSampleLecture } from './sample'
import type { PlayerLecture } from './timeline'

/** /courses/:id/lectures/:n/slides/:k, with k counted from 1. */
export function PlayerPage({ load = loadSampleLecture }: { load?: () => PlayerLecture }) {
  const { courseId, lectureNumber, slide } = useParams()
  const navigate = useNavigate()
  const lecture = load()
  const initialIndex = Math.max(Number.parseInt(slide ?? '1', 10) || 1, 1) - 1

  const onIndexChange = useCallback((index: number) => {
    navigate(`/courses/${courseId}/lectures/${lectureNumber}/slides/${index + 1}`, { replace: true })
  }, [courseId, lectureNumber, navigate])

  return <main className="page-content">
    <p className="query-message" role="note">Sample lecture: course players arrive with the pipeline adapters.</p>
    <Player lecture={lecture} initialIndex={initialIndex} onIndexChange={onIndexChange} />
  </main>
}
