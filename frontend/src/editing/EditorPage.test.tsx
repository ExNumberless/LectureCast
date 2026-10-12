import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { EditorPage } from './EditorPage'

const node = { id: 7, stage: 'transcript', lecture: 11, lecture_title: 'Intro', status: 'succeeded', settings_hash: '', inputs_hash: '', frozen: false, error: '', run_by_email: null, latest_run: null, updated_at: '' }
const edit = { id: 1, n: 2, text: 'Edited $x^2$.\n', edited_by_email: 'owner@example.com', edited_at: '2026-10-12T02:00:00Z' }

let sections: object
let saved: unknown

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

beforeEach(() => {
  saved = undefined
  sections = {
    node, editable: true, reason: null,
    sections: [
      { n: 1, title: 'Overview', text: 'Hi <script>window.pwned = 1</script> <img src=x onerror="window.pwned = 1">\n', original: 'Hi\n', edits: [] },
      { n: 2, title: 'Details', text: 'Edited $x^2$.\n', original: 'Original text.\n', edits: [edit] },
    ],
  }
  vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => {
    if (path === '/api/auth/csrf/') return respond({ csrf_cookie_name: 'csrftoken' })
    if (path === '/api/nodes/7/sections') return respond(sections)
    if (path === '/api/nodes/7/sections/1' && init?.method === 'PUT') {
      saved = JSON.parse(init.body as string)
      return respond({ node, edit: { ...edit, n: 1 }, stale_nodes: [{ ...node, id: 8, stage: 'tts' }, { ...node, id: 9, stage: 'assemble' }] })
    }
    return respond({ detail: 'Not found' }, 404)
  }))
})

afterEach(() => vi.unstubAllGlobals())

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>
    <MemoryRouter initialEntries={['/courses/3/nodes/7/edit']}><Routes><Route path="/courses/:courseId/nodes/:nodeId/edit" element={<EditorPage />} /></Routes></MemoryRouter>
  </QueryClientProvider>)
}

describe('EditorPage', () => {
  it('previews section Markdown without rendering raw HTML', async () => {
    const { container } = renderEditor()
    await screen.findByRole('heading', { name: 'Edit transcript: Intro' })
    const preview = container.querySelector('.editor-preview')!
    expect(preview.querySelector('script')).toBeNull()
    expect(preview.querySelector('img')).toBeNull()
    expect(container.querySelector('[onerror]')).toBeNull()
  })

  it('shows edited sections, their author and a diff against the original', async () => {
    const { container } = renderEditor()
    const nav = await screen.findByRole('navigation', { name: 'Sections' })
    expect(within(nav).getByRole('button', { name: /\[2\] Details.*edited/ })).toBeInTheDocument()

    fireEvent.click(within(nav).getByRole('button', { name: /\[2\] Details/ }))
    expect(container.querySelector('.editor-preview .katex')).not.toBeNull()
    expect(screen.getByText(/Last edited by owner@example.com/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Changes from the original' }))
    const diff = screen.getByLabelText('Changes from the original', { selector: 'pre' })
    expect(within(diff).getByText('Original text.').closest('div')).toHaveClass('diff-removed')
    expect(within(diff).getByText('Edited $x^2$.').closest('div')).toHaveClass('diff-added')
  })

  it('saves a section and lists the stages that became stale', async () => {
    renderEditor()
    const textarea = await screen.findByRole('textbox', { name: 'Markdown' })
    expect(screen.getByRole('button', { name: 'Save section' })).toBeDisabled()

    fireEvent.change(textarea, { target: { value: 'Hello there.\n' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save section' }))

    expect(await screen.findByText('Saved. Now stale: Narration (Intro), Slideshow (Intro).')).toBeInTheDocument()
    expect(saved).toEqual({ text: 'Hello there.\n' })
  })

  it('is read-only for frozen output', async () => {
    sections = { ...sections, editable: false, reason: 'This output is frozen. Fork the course to change it.' }
    renderEditor()
    expect(await screen.findByRole('note')).toHaveTextContent('Fork the course')
    expect(screen.getByRole('textbox', { name: 'Markdown' })).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: 'Save section' })).not.toBeInTheDocument()
  })
})
