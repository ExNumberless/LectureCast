import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { apiRequest } from '../api/client'
import type { components } from '../api/schema'
import { STAGE_LABELS } from '../pipeline/stages'
import { MarkdownSlide } from '../player/SlideView'
import { diffLines } from './diff'

type NodeSections = components['schemas']['NodeSections']
type Section = components['schemas']['NodeSection']
type SaveResponse = components['schemas']['SectionUpdateResponse']

/** /courses/:courseId/nodes/:nodeId/edit: edit a materials or transcript node one `## [N]` section at a time. */
export function EditorPage() {
  const { courseId, nodeId } = useParams()
  const [selected, setSelected] = useState<number | null>(null)
  const query = useQuery({
    queryKey: ['node-sections', nodeId],
    queryFn: () => apiRequest<NodeSections>(`/api/nodes/${nodeId}/sections`),
  })

  if (query.isPending) return <main className="page-content"><p className="query-message" role="status">Loading the sections…</p></main>
  if (query.isError) return <main className="page-content"><p className="error-notice" role="alert">{query.error.message}</p></main>

  const { node, sections, editable, reason } = query.data
  const current = sections.find((section) => section.n === selected) ?? sections[0]

  return <main className="page-content editor-page">
    <div className="page-header"><div>
      <p className="eyebrow"><Link to={`/courses/${courseId}`}>BACK TO THE PIPELINE</Link></p>
      <h1>Edit {STAGE_LABELS[node.stage].toLowerCase()}{node.lecture_title ? `: ${node.lecture_title}` : ''}</h1>
      {!editable && reason && <p className="query-message" role="note">{reason}</p>}
    </div></div>
    <div className="editor-layout">
      <nav aria-label="Sections"><ol className="section-list">{sections.map((section) => <li key={section.n}>
        <button type="button" aria-current={section.n === current?.n ? 'true' : undefined} onClick={() => setSelected(section.n)}>
          [{section.n}] {section.title}{section.text !== section.original && <span className="edited-mark"> · edited</span>}
        </button>
      </li>)}</ol></nav>
      {current
        ? <SectionEditor key={`${current.n}:${current.edits.length}`} nodeId={node.id} section={current} editable={editable} />
        : <p className="query-message">This output has no sections.</p>}
    </div>
  </main>
}

function SectionEditor({ nodeId, section, editable }: { nodeId: number; section: Section; editable: boolean }) {
  const queryClient = useQueryClient()
  const [text, setText] = useState(section.text)
  const [view, setView] = useState<'preview' | 'diff'>('preview')
  const save = useMutation({
    mutationFn: () => apiRequest<SaveResponse>(`/api/nodes/${nodeId}/sections/${section.n}`, { method: 'PUT', body: { text } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['node-sections', String(nodeId)] })
      await queryClient.invalidateQueries({ queryKey: ['course-graph'] })
    },
  })
  const changed = text !== section.text
  const latest = section.edits.at(-1)

  return <section className="section-editor" aria-label={`Section ${section.n}: ${section.title}`}>
    <label className="editor-field">Markdown
      <textarea value={text} onChange={(event) => setText(event.target.value)} readOnly={!editable} rows={16} spellCheck />
    </label>
    <div className="editor-tabs" role="group" aria-label="View">
      <button type="button" aria-pressed={view === 'preview'} onClick={() => setView('preview')}>Preview</button>
      <button type="button" aria-pressed={view === 'diff'} onClick={() => setView('diff')}>Changes from the original</button>
    </div>
    {view === 'preview'
      ? <div className="editor-preview"><MarkdownSlide markdown={text} /></div>
      : <SectionDiff original={section.original} text={text} />}
    {latest && <p className="field-help">Last edited by {latest.edited_by_email ?? 'a former user'} on {new Date(latest.edited_at).toLocaleString()}. {section.edits.length} edit{section.edits.length === 1 ? '' : 's'} since generation.</p>}
    {save.isError && <p className="error-notice" role="alert">{save.error.message}</p>}
    {save.isSuccess && save.data.edit && <p role="status">
      Saved. {save.data.stale_nodes.length
        ? `Now stale: ${save.data.stale_nodes.map((node) => `${STAGE_LABELS[node.stage]}${node.lecture_title ? ` (${node.lecture_title})` : ''}`).join(', ')}.`
        : 'No later stages had run yet.'}
    </p>}
    {editable && <div className="dialog-actions">
      <button type="button" className="button" disabled={!changed} onClick={() => setText(section.text)}>Discard changes</button>
      <button type="button" className="button button-primary" disabled={!changed || save.isPending} onClick={() => save.mutate()}>Save section</button>
    </div>}
  </section>
}

function SectionDiff({ original, text }: { original: string; text: string }) {
  const lines = diffLines(original, text)
  if (lines.every((line) => line.kind === 'same')) return <p className="query-message">No changes from the generated original.</p>
  return <pre className="section-diff" aria-label="Changes from the original">{lines.map((line, i) => <div key={i} className={`diff-${line.kind}`}>
    <span aria-hidden="true">{line.kind === 'added' ? '+' : line.kind === 'removed' ? '−' : ' '} </span>
    <span className="sr-only">{line.kind === 'added' ? 'Added: ' : line.kind === 'removed' ? 'Removed: ' : ''}</span>{line.text}
  </div>)}</pre>
}
