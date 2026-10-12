import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { apiRequest } from '../api/client'
import type { components } from '../api/schema'
import { STAGE_LABELS } from '../pipeline/stages'
import type { StageName } from '../pipeline/stages'

type CatalogCourse = components['schemas']['CatalogCourse']

const COVERAGE: StageName[] = ['materials', 'transcript', 'tts', 'assemble']

export function CatalogPage() {
  const catalog = useQuery({
    queryKey: ['catalog'],
    queryFn: () => apiRequest<CatalogCourse[]>('/api/catalog'),
  })
  return <main className="page-content">
    <div className="page-header"><div>
      <p className="eyebrow">SHARED CATALOG</p><h1>Catalog</h1>
      <p className="page-description">Openly licensed courses that other people have turned into narrated lectures.</p>
    </div></div>
    {catalog.isPending && <p className="query-message" role="status">Loading the catalog…</p>}
    {catalog.isError && <p className="error-notice" role="alert">{catalog.error.message}</p>}
    {catalog.data?.length === 0 && <p className="query-message">No published courses have a playable lecture yet.</p>}
    <div className="catalog-list">{catalog.data?.map((course) => <CatalogCard key={course.id} course={course} />)}</div>
  </main>
}

function CatalogCard({ course }: { course: CatalogCourse }) {
  const [reporting, setReporting] = useState(false)
  return <article className="catalog-card" aria-labelledby={`catalog-${course.id}`}>
    <header>
      <h2 id={`catalog-${course.id}`}>{course.title}</h2>
      <p className="field-help">
        {course.license_name} · {course.attribution}
        {course.source_url && <> · <a href={course.source_url} rel="noopener noreferrer nofollow" target="_blank">Source</a></>}
      </p>
    </header>
    <dl className="coverage-totals">{COVERAGE.map((stage) => <div key={stage}>
      <dt>{STAGE_LABELS[stage]}</dt><dd>{course.totals[stage] ?? 0}/{course.lectures.length}</dd>
    </div>)}</dl>
    <table className="coverage-grid" aria-label={`Coverage of ${course.title}`}>
      <thead><tr><th scope="col">Lecture</th>{COVERAGE.map((stage) => <th scope="col" key={stage}>{STAGE_LABELS[stage]}</th>)}</tr></thead>
      <tbody>{course.lectures.map((lecture) => <tr key={lecture.number}>
        <th scope="row">{lecture.number}. {lecture.title}</th>
        {COVERAGE.map((stage) => <td key={stage}>{lecture.stages.includes(stage)
          ? <span className="coverage-dot done" aria-label="Done">●</span>
          : <span className="coverage-dot" aria-label="Not yet">○</span>}</td>)}
      </tr>)}</tbody>
    </table>
    {course.contributors.length > 0 && <p className="field-help">Made by: {course.contributors.map((item) => `${STAGE_LABELS[item.stage as StageName] ?? item.stage}: ${item.names.join(', ')}`).join(' · ')}</p>}
    {reporting
      ? <ReportForm courseId={course.id} onDone={() => setReporting(false)} />
      : <button type="button" className="button" onClick={() => setReporting(true)}>Report a problem</button>}
  </article>
}

function ReportForm({ courseId, onDone }: { courseId: number; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const report = useMutation({
    mutationFn: () => apiRequest(`/api/catalog/${courseId}/reports`, { method: 'POST', body: { reason } }),
  })
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    report.mutate()
  }
  if (report.isSuccess) return <p role="status">Thanks. A moderator will look at your report.</p>
  return <form className="report-form" onSubmit={submit}>
    <label>What's wrong?<textarea required value={reason} onChange={(event) => setReason(event.target.value)} rows={3} /></label>
    {report.isError && <p className="error-notice" role="alert">{report.error.message}</p>}
    <div className="dialog-actions">
      <button type="button" className="button" onClick={onDone}>Cancel</button>
      <button type="submit" className="button button-primary" disabled={report.isPending}>Send report</button>
    </div>
  </form>
}
