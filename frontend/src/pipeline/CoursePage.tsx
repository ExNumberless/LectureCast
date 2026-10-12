import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router'

import { apiRequest } from '../api/client'
import type { components } from '../api/schema'
import {
  STAGE_LABELS, STATUS_LABELS, LECTURE_STAGES, indexNodes, isActive, isCourseStage, nodeKey, progressText,
  sourceStage, stageColumns,
} from './stages'
import type { Course, Lecture, StageName, StageNode } from './stages'

type Graph = components['schemas']['CourseGraph']
type Estimate = components['schemas']['CourseEstimate']
type RunRequest = { stage: StageName; lecture_ids?: number[] }
type LogEntry = { at?: string; message?: string }
type UsageEntry = { vendor?: string; model?: string } & Record<string, unknown>
type Selection = { stage: StageName; lecture: Lecture | null }

export function CoursePage() {
  const courseId = Number(useParams().courseId)
  const [selected, setSelected] = useState<Selection | null>(null)
  const [runDraft, setRunDraft] = useState<RunRequest | null>(null)
  const courseQuery = useQuery({
    queryKey: ['course', courseId],
    queryFn: () => apiRequest<Course>(`/api/courses/${courseId}/`),
  })
  const graphQuery = useQuery({
    queryKey: ['course-graph', courseId],
    queryFn: () => apiRequest<Graph>(`/api/courses/${courseId}/graph`),
    // Follow running work until every node settles.
    refetchInterval: (query) => query.state.data?.nodes.some((node) => isActive(node.status)) ? 2000 : false,
  })

  if (courseQuery.isPending || graphQuery.isPending) return <main className="page-content"><p className="query-message" role="status">Loading the course…</p></main>
  if (courseQuery.isError) return <main className="page-content"><p className="error-notice" role="alert">{courseQuery.error.message}</p></main>
  if (graphQuery.isError) return <main className="page-content"><p className="error-notice" role="alert">{graphQuery.error.message}</p></main>

  const course = courseQuery.data
  const graph = graphQuery.data
  const nodes = indexNodes(graph.nodes)
  const source = nodes.get(nodeKey(sourceStage(course), null))
  const review = nodes.get(nodeKey('review', null))
  const included = graph.lectures.filter((lecture) => lecture.included)
  const selectedNode = selected ? nodes.get(nodeKey(selected.stage, selected.lecture?.id ?? null)) : undefined

  return <main className="page-content">
    <div className="page-header">
      <div><p className="eyebrow"><Link to="/courses">MY COURSES</Link></p><h1>{course.title}</h1></div>
      {review?.status === 'succeeded'
        ? <button
          className="button button-primary"
          type="button"
          disabled={included.length === 0}
          onClick={() => setRunDraft({ stage: 'assemble', lecture_ids: included.map((lecture) => lecture.id) })}
        >Run lectures…</button>
        : <button
          className="button button-primary"
          type="button"
          disabled={isActive(source?.status)}
          onClick={() => setRunDraft({ stage: sourceStage(course) })}
        >{STAGE_LABELS[sourceStage(course)]} course…</button>}
    </div>

    <PipelineGrid course={course} graph={graph} onSelect={setSelected} />

    {source?.status === 'succeeded' && <ReviewPanel key={graph.lectures.map((lecture) => lecture.id).join()} courseId={courseId} lectures={graph.lectures} reviewed={review?.status === 'succeeded'} />}

    {selected && <NodeDetail
      selection={selected}
      node={selectedNode}
      onClose={() => setSelected(null)}
      onRun={(request) => setRunDraft(request)}
    />}

    {runDraft && <RunDialog
      course={course}
      lectures={included}
      initial={runDraft}
      onClose={() => setRunDraft(null)}
    />}
  </main>
}

function PipelineGrid({ course, graph, onSelect }: { course: Course; graph: Graph; onSelect: (selection: Selection) => void }) {
  const columns = stageColumns(course)
  const nodes = indexNodes(graph.nodes)
  const lectures = graph.lectures.filter((lecture) => lecture.included)

  function cell(stage: StageName, lecture: Lecture | null) {
    const node = nodes.get(nodeKey(stage, lecture?.id ?? null))
    const status = node?.status ?? 'pending'
    const progress = progressText(node)
    const where = lecture ? `lecture ${lecture.number}` : 'the course'
    return <td key={stage}>
      <button
        type="button"
        className={`node node-${status}`}
        aria-label={`${STAGE_LABELS[stage]} for ${where}: ${STATUS_LABELS[status]}`}
        onClick={() => onSelect({ stage, lecture })}
      >{STATUS_LABELS[status]}{progress && <span className="node-progress"> {progress}</span>}{node?.frozen && ' 🔒'}</button>
    </td>
  }

  return <div className="pipeline-grid-wrap">
    <table className="pipeline-grid" aria-label="Pipeline">
      <thead><tr><th scope="col">Lecture</th>{columns.map((stage) => <th scope="col" key={stage}>{STAGE_LABELS[stage]}</th>)}</tr></thead>
      <tbody>
        <tr>
          <th scope="row">Course</th>
          {columns.map((stage) => isCourseStage(stage) ? cell(stage, null) : <td key={stage} />)}
        </tr>
        {lectures.map((lecture) => <tr key={lecture.id}>
          <th scope="row">{lecture.number}. {lecture.title || lecture.name}</th>
          {columns.map((stage) => isCourseStage(stage) ? <td key={stage} /> : cell(stage, lecture))}
        </tr>)}
      </tbody>
    </table>
    {lectures.length === 0 && <p className="query-message">Lectures appear here once the course source has been fetched and reviewed.</p>}
  </div>
}

function NodeDetail({ selection, node, onClose, onRun }: {
  selection: Selection
  node: StageNode | undefined
  onClose: () => void
  onRun: (request: RunRequest) => void
}) {
  const { stage, lecture } = selection
  const status = node?.status ?? 'pending'
  const run = node?.latest_run
  const log = (run?.log as LogEntry[] | undefined) ?? []
  const usage = (run?.usage as UsageEntry[] | undefined) ?? []
  const request: RunRequest = lecture ? { stage, lecture_ids: [lecture.id] } : { stage }
  const runnable = stage !== 'review' && !isActive(status) && !(node?.frozen)

  return <aside className="node-detail" aria-label="Stage details">
    <header>
      <h2>{STAGE_LABELS[stage]} · {lecture ? `${lecture.number}. ${lecture.title || lecture.name}` : 'Course'}</h2>
      <button type="button" className="icon-button" aria-label="Close details" onClick={onClose}>×</button>
    </header>
    <dl>
      <dt>Status</dt><dd>{STATUS_LABELS[status]}{progressText(node) && ` (${progressText(node)})`}</dd>
      <dt>Run by</dt><dd>{node?.run_by_email ?? '—'}</dd>
    </dl>
    {node?.error && <p className="error-notice" role="alert">{node.error}</p>}
    {stage === 'review' && <p>Review the lecture list below to complete this step.</p>}
    <div className="node-actions">
      {status === 'failed'
        ? <button type="button" className="button button-primary" disabled={!runnable} onClick={() => onRun(request)}>Retry</button>
        : <button type="button" className="button button-primary" disabled={!runnable} onClick={() => onRun(request)}>Run</button>}
      <button type="button" className="button" disabled title="Forking arrives with the catalog.">Fork</button>
    </div>
    <h3>Log</h3>
    {log.length ? <ol className="node-log">{log.map((entry, i) => <li key={i}>
      {entry.at && <time dateTime={entry.at}>{new Date(entry.at).toLocaleTimeString()}</time>} {entry.message}
    </li>)}</ol> : <p className="query-message">No log yet.</p>}
    <h3>Usage</h3>
    {usage.length ? <ul className="node-usage">{usage.map((entry, i) => <li key={i}>
      {entry.vendor} {entry.model}: {Object.entries(entry).filter(([key, value]) => !['vendor', 'model'].includes(key) && value).map(([key, value]) => `${key.replaceAll('_', ' ')} ${String(value)}`).join(', ')}
    </li>)}</ul> : <p className="query-message">No billable usage.</p>}
  </aside>
}

function RunDialog({ course, lectures, initial, onClose }: {
  course: Course
  lectures: Lecture[]
  initial: RunRequest
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [stage, setStage] = useState<StageName>(initial.stage)
  const [lectureIds, setLectureIds] = useState<number[]>(initial.lecture_ids ?? lectures.map((lecture) => lecture.id))
  const courseStage = isCourseStage(stage)
  const request: RunRequest = courseStage ? { stage } : { stage, lecture_ids: lectureIds }
  const estimate = useMutation({
    mutationFn: () => apiRequest<Estimate>(`/api/courses/${course.id}/estimate`, { method: 'POST', body: request }),
  })
  const run = useMutation({
    mutationFn: () => apiRequest(`/api/courses/${course.id}/runs`, { method: 'POST', body: request }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['course-graph', course.id] })
      onClose()
    },
  })
  const estimateReason = (estimate.data?.estimate as { reason?: string } | undefined)?.reason

  function changeStage(value: StageName) {
    setStage(value)
    estimate.reset()
  }

  function toggleLecture(id: number) {
    setLectureIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
    estimate.reset()
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (estimate.isSuccess) run.mutate()
    else estimate.mutate()
  }

  return <div className="dialog-backdrop">
    <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="run-dialog-title" onSubmit={submit}>
      <h2 id="run-dialog-title">Run the pipeline</h2>
      <label>Run up to<select value={stage} onChange={(event) => changeStage(event.target.value as StageName)}>
        {[sourceStage(course), ...LECTURE_STAGES].map((name) => <option key={name} value={name}>{STAGE_LABELS[name]}</option>)}
      </select></label>
      {!courseStage && <fieldset>
        <legend>Lectures</legend>
        {lectures.map((lecture) => <label key={lecture.id} className="checkbox-row">
          <input type="checkbox" checked={lectureIds.includes(lecture.id)} onChange={() => toggleLecture(lecture.id)} />
          {lecture.number}. {lecture.title || lecture.name}
        </label>)}
      </fieldset>}

      {estimate.isSuccess && <section aria-label="Estimate">
        <h3>What will run</h3>
        <ul className="estimate-list">{estimate.data.nodes.map((node) => <li key={`${node.stage}:${node.lecture_id}`}>
          {STAGE_LABELS[node.stage as StageName] ?? node.stage}{node.lecture_title ? ` · ${node.lecture_title}` : ''}: {node.action === 'reuse' ? 'up to date' : 'will run'}
        </li>)}</ul>
        <p className="field-help">{estimateReason ?? 'Cost estimate unavailable.'}</p>
      </section>}
      {(estimate.isError || run.isError) && <p className="error-notice" role="alert">{(estimate.error ?? run.error)?.message}</p>}

      <div className="dialog-actions">
        <button type="button" className="button" onClick={onClose}>Cancel</button>
        <button type="submit" className="button button-primary" disabled={estimate.isPending || run.isPending || (!courseStage && lectureIds.length === 0)}>
          {estimate.isSuccess ? 'Confirm and run' : 'Estimate'}
        </button>
      </div>
    </form>
  </div>
}

type ReviewRow = { id: number; included: boolean; number: number; title: string }

function ReviewPanel({ courseId, lectures, reviewed }: { courseId: number; lectures: Lecture[]; reviewed: boolean }) {
  const queryClient = useQueryClient()
  const [rows, setRows] = useState<ReviewRow[]>(() => lectures.map((lecture) => ({
    id: lecture.id, included: lecture.included, number: lecture.number, title: lecture.title,
  })))
  const save = useMutation({
    mutationFn: () => apiRequest(`/api/courses/${courseId}/review`, {
      method: 'POST',
      body: { lectures: rows.filter((row) => row.included).map(({ id, number, title }) => ({ id, number, title })) },
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['course-graph', courseId] }),
  })

  function update(id: number, change: Partial<ReviewRow>) {
    setRows((current) => current.map((row) => row.id === id ? { ...row, ...change } : row))
  }

  return <details className="review-panel" open={!reviewed}>
    <summary>{reviewed ? 'Lecture list (reviewed)' : 'Review the lecture list'}</summary>
    <form onSubmit={(event) => { event.preventDefault(); save.mutate() }}>
      <table>
        <thead><tr><th scope="col">Include</th><th scope="col">Number</th><th scope="col">Title</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.id}>
          <td><input type="checkbox" aria-label={`Include ${row.title || row.number}`} checked={row.included} onChange={(event) => update(row.id, { included: event.target.checked })} /></td>
          <td><input type="number" min={1} aria-label="Number" value={row.number} onChange={(event) => update(row.id, { number: Number(event.target.value) })} /></td>
          <td><input aria-label="Title" value={row.title} onChange={(event) => update(row.id, { title: event.target.value })} /></td>
        </tr>)}</tbody>
      </table>
      {save.isError && <p className="error-notice" role="alert">{save.error.message}</p>}
      <button type="submit" className="button button-primary" disabled={save.isPending || !rows.some((row) => row.included)}>Save lecture list</button>
    </form>
  </details>
}
