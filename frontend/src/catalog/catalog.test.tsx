import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CatalogPage } from './CatalogPage'
import { PublishPanel } from './PublishPanel'

const entry = {
  id: 3, title: 'Algorithms', provider: 'website', source_url: 'https://example.edu/algo', license: 'CC-BY-4.0',
  license_name: 'CC BY 4.0', attribution: 'Notes by Prof. Example.', published_at: null, playable_lectures: 1,
  totals: { materials: 2, transcript: 1, tts: 1, render: 0, assemble: 0 },
  lectures: [{ number: 1, title: 'Intro', stages: ['materials', 'transcript', 'tts'] }, { number: 2, title: 'Sorting', stages: ['materials'] }],
  contributors: [{ stage: 'tts', names: ['Ada Lovelace'] }],
}

let publication: object | null
let posts: { path: string; body: unknown }[]

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

beforeEach(() => {
  publication = null
  posts = []
  vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => {
    if (init?.method === 'POST' && path !== '/api/auth/csrf/') {
      const body = JSON.parse(init.body as string)
      posts.push({ path, body })
      if (path === '/api/courses/3/publication') return respond({ id: 1, course: 3, status: 'pending', license: body.license, license_name: 'CC BY 4.0', attribution: body.attribution, requested_at: '', reviewed_at: null, review_note: '' }, 201)
      return respond({ id: 1 }, 201)
    }
    if (path === '/api/auth/csrf/') return respond({ csrf_cookie_name: 'csrftoken' })
    if (path === '/api/catalog') return respond([entry])
    if (path === '/api/catalog/licenses') return respond([{ id: 'CC-BY-4.0', name: 'CC BY 4.0' }, { id: 'CC0-1.0', name: 'CC0 1.0' }])
    if (path === '/api/courses/3/publication') return publication ? respond(publication) : respond({ detail: 'Not found.' }, 404)
    return respond({ detail: 'Not found.' }, 404)
  }))
})

afterEach(() => vi.unstubAllGlobals())

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>)
}

describe('CatalogPage', () => {
  it('shows each course with its license, coverage and contributors', async () => {
    wrap(<CatalogPage />)
    const card = await screen.findByRole('article', { name: 'Algorithms' })
    expect(within(card).getByText(/CC BY 4.0 · Notes by Prof. Example./)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Source' })).toHaveAttribute('rel', 'noopener noreferrer nofollow')
    const grid = within(card).getByRole('table', { name: 'Coverage of Algorithms' })
    const sorting = within(grid).getByRole('row', { name: /2\. Sorting/ })
    expect(within(sorting).getAllByLabelText('Done')).toHaveLength(1)
    expect(within(card).getByText(/Narration: Ada Lovelace/)).toBeInTheDocument()
  })

  it('sends a report to the moderators', async () => {
    wrap(<CatalogPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Report a problem' }))
    fireEvent.change(screen.getByRole('textbox', { name: "What's wrong?" }), { target: { value: 'Wrong slides' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
    expect(await screen.findByText(/A moderator will look/)).toBeInTheDocument()
    expect(posts).toEqual([{ path: '/api/catalog/3/reports', body: { reason: 'Wrong slides' } }])
  })
})

describe('PublishPanel', () => {
  it('asks for an open license and attribution, then shows the pending review', async () => {
    wrap(<PublishPanel courseId={3} reviewed />)
    const license = await screen.findByRole('combobox', { name: 'License' })
    await within(license).findByRole('option', { name: 'CC BY 4.0' })
    fireEvent.change(license, { target: { value: 'CC-BY-4.0' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Attribution' }), { target: { value: 'Notes by Prof. Example.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Request publication' }))
    expect(await screen.findByText(/Waiting for review/)).toBeInTheDocument()
    expect(posts).toEqual([{ path: '/api/courses/3/publication', body: { license: 'CC-BY-4.0', attribution: 'Notes by Prof. Example.' } }])
  })

  it('waits for the lecture review and shows published courses', async () => {
    const { unmount } = wrap(<PublishPanel courseId={3} reviewed={false} />)
    expect(await screen.findByText('Review the lecture list before publishing.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Request publication' })).not.toBeInTheDocument()
    unmount()

    publication = { id: 1, course: 3, status: 'approved', license: 'CC-BY-4.0', license_name: 'CC BY 4.0', attribution: 'x', requested_at: '', reviewed_at: '', review_note: '' }
    wrap(<PublishPanel courseId={3} reviewed />)
    expect(await screen.findByText(/Published under CC BY 4.0/)).toBeInTheDocument()
  })
})
