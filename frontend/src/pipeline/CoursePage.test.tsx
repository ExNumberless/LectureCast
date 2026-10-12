import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CoursePage } from './CoursePage'

const course = { id: 3, title: 'Algorithms', provider: 'website' }
const lectures = [
  { id: 11, number: 1, name: 'lecture-01', title: 'Intro', date: null, included: true, audio: null, duration_ms: null },
  { id: 12, number: 2, name: 'lecture-02', title: 'Sorting', date: null, included: true, audio: null, duration_ms: null },
]

function node(id: number, stage: string, lecture: number | null, status: string, extra: object = {}) {
  return { id, stage, lecture, lecture_title: null, status, settings_hash: '', inputs_hash: '', frozen: false, error: '', run_by_email: null, latest_run: null, updated_at: '', ...extra }
}

const reviewedGraph = {
  course_id: 3,
  lectures,
  nodes: [
    node(1, 'fetch', null, 'succeeded', { run_by_email: 'owner@example.com' }),
    node(2, 'review', null, 'succeeded'),
    node(3, 'materials', 11, 'running', { latest_run: { id: 9, stage: 'materials', lecture_id: 11, lecture_title: 'Intro', status: 'running', progress: { name: 'materials', done: 2, total: 5 }, log: [], usage: [], error: '' } }),
    node(4, 'transcript', 12, 'failed', {
      error: 'RuntimeError: model unavailable',
      run_by_email: 'owner@example.com',
      latest_run: {
        id: 10, stage: 'transcript', lecture_id: 12, lecture_title: 'Sorting', status: 'failed', progress: {}, error: 'RuntimeError: model unavailable',
        log: [{ at: '2026-10-12T02:00:00Z', message: 'Fake transcript stage started.' }],
        usage: [{ vendor: 'anthropic', model: 'claude', input_tokens: 1200, output_tokens: 300 }],
      },
    }),
  ],
}

let graph: object
let requests: { path: string; method: string; body: unknown }[]

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

beforeEach(() => {
  graph = reviewedGraph
  requests = []
  vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    requests.push({ path, method, body: init?.body ? JSON.parse(init.body as string) : undefined })
    if (path === '/api/auth/csrf/') return respond({ csrf_cookie_name: 'csrftoken' })
    if (path === '/api/courses/3/') return respond(course)
    if (path === '/api/courses/3/graph') return respond(graph)
    if (path === '/api/courses/3/estimate') return respond({
      targets: {},
      nodes: [{ stage: 'materials', lecture_id: 12, lecture_title: 'Sorting', status: 'succeeded', action: 'reuse' }, { stage: 'transcript', lecture_id: 12, lecture_title: 'Sorting', status: 'failed', action: 'run' }],
      estimate: { available: false, reason: 'Cost estimates are not enabled yet.' },
    })
    if (path === '/api/courses/3/runs') return respond({ id: 1 }, 202)
    if (path === '/api/courses/3/review') return respond({})
    return respond({ detail: 'Not found' }, 404)
  }))
})

afterEach(() => vi.unstubAllGlobals())

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>
    <MemoryRouter initialEntries={['/courses/3']}><Routes><Route path="/courses/:courseId" element={<CoursePage />} /></Routes></MemoryRouter>
  </QueryClientProvider>)
}

describe('CoursePage', () => {
  it('shows a lecture × stage grid with node status and progress', async () => {
    renderPage()
    const grid = await screen.findByRole('table', { name: 'Pipeline' })
    expect(within(grid).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(
      ['Lecture', 'Fetch', 'Review', 'Materials', 'Transcript', 'Narration', 'Slides', 'Slideshow'],
    )
    expect(within(grid).getByRole('button', { name: 'Fetch for the course: Done' })).toBeInTheDocument()
    expect(within(grid).getByRole('button', { name: 'Materials for lecture 1: Running' })).toHaveTextContent('Running 2/5')
    expect(within(grid).getByRole('button', { name: 'Transcript for lecture 2: Failed' })).toBeInTheDocument()
    expect(within(grid).getByRole('button', { name: 'Slideshow for lecture 2: Not started' })).toBeInTheDocument()
  })

  it('shows a node’s log, usage and contributor, and retries it after an estimate', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Transcript for lecture 2: Failed' }))
    const detail = screen.getByRole('complementary', { name: 'Stage details' })
    expect(within(detail).getByRole('alert')).toHaveTextContent('model unavailable')
    expect(within(detail).getByText('owner@example.com')).toBeInTheDocument()
    expect(within(detail).getByText(/Fake transcript stage started/)).toBeInTheDocument()
    expect(within(detail).getByText(/anthropic claude: input tokens 1200, output tokens 300/)).toBeInTheDocument()
    expect(within(detail).getByRole('button', { name: 'Fork' })).toBeDisabled()

    fireEvent.click(within(detail).getByRole('button', { name: 'Retry' }))
    const dialog = screen.getByRole('dialog', { name: 'Run the pipeline' })
    expect(within(dialog).getByRole('checkbox', { name: '1. Intro' })).not.toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: '2. Sorting' })).toBeChecked()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Estimate' }))
    expect(await within(dialog).findByText('Transcript · Sorting: will run')).toBeInTheDocument()
    expect(within(dialog).getByText('Materials · Sorting: up to date')).toBeInTheDocument()
    expect(within(dialog).getByText('Cost estimates are not enabled yet.')).toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm and run' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const posts = requests.filter((request) => request.method === 'POST')
    expect(posts.map((request) => [request.path, request.body])).toEqual([
      ['/api/courses/3/estimate', { stage: 'transcript', lecture_ids: [12] }],
      ['/api/courses/3/runs', { stage: 'transcript', lecture_ids: [12] }],
    ])
  })

  it('changing the selection asks for a new estimate', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Run lectures…' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Estimate' }))
    await within(dialog).findByRole('button', { name: 'Confirm and run' })
    fireEvent.click(within(dialog).getByRole('checkbox', { name: '1. Intro' }))
    expect(within(dialog).getByRole('button', { name: 'Estimate' })).toBeInTheDocument()
  })

  it('starts with the source stage and the lecture review before any lecture runs', async () => {
    graph = { course_id: 3, lectures, nodes: [node(1, 'fetch', null, 'succeeded'), node(2, 'review', null, 'pending')] }
    renderPage()
    expect(await screen.findByRole('button', { name: 'Fetch course…' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Run lectures…' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Include Intro' }))
    fireEvent.change(screen.getAllByRole('textbox', { name: 'Title' })[1], { target: { value: 'Sorting and searching' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save lecture list' }))
    await waitFor(() => expect(requests.some((request) => request.path === '/api/courses/3/review')).toBe(true))
    expect(requests.find((request) => request.path === '/api/courses/3/review')?.body).toEqual({
      lectures: [{ id: 12, number: 2, title: 'Sorting and searching' }],
    })
  })
})
