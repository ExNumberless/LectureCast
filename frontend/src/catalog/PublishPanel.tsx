import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { apiRequest } from '../api/client'
import type { components } from '../api/schema'

type Publication = components['schemas']['Publication']
type License = components['schemas']['License']

async function loadPublication(courseId: number) {
  try {
    return await apiRequest<Publication>(`/api/courses/${courseId}/publication`)
  } catch {
    return null // Not requested yet.
  }
}

/** Publish the course to the catalog, any time after its lecture list is reviewed. */
export function PublishPanel({ courseId, reviewed }: { courseId: number; reviewed: boolean }) {
  const queryClient = useQueryClient()
  const publication = useQuery({ queryKey: ['publication', courseId], queryFn: () => loadPublication(courseId) })
  const licenses = useQuery({ queryKey: ['licenses'], queryFn: () => apiRequest<License[]>('/api/catalog/licenses') })
  const [license, setLicense] = useState('')
  const [attribution, setAttribution] = useState('')
  const request = useMutation({
    mutationFn: () => apiRequest<Publication>(`/api/courses/${courseId}/publication`, { method: 'POST', body: { license, attribution } }),
    onSuccess: (data) => queryClient.setQueryData(['publication', courseId], data),
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    request.mutate()
  }

  const current = publication.data
  const canRequest = reviewed && (!current || current.status === 'rejected')

  return <section className="publish-panel" aria-labelledby="publish-title">
    <h2 id="publish-title">Catalog</h2>
    {current?.status === 'pending' && <p role="status">Waiting for review. Once approved, the course's finished outputs are published and frozen.</p>}
    {current?.status === 'approved' && <p role="status">Published under {current.license_name}. New outputs are added to the catalog when their runs finish.</p>}
    {current?.status === 'unpublished' && <p role="status">An admin unpublished this course{current.review_note ? `: ${current.review_note}` : '.'}</p>}
    {current?.status === 'rejected' && <p role="alert">Not approved{current.review_note ? `: ${current.review_note}` : '.'} You can change the license or attribution and ask again.</p>}
    {!reviewed && <p className="query-message">Review the lecture list before publishing.</p>}
    {canRequest && <form onSubmit={submit} className="publish-form">
      <label>License
        <select required value={license} onChange={(event) => setLicense(event.target.value)}>
          <option value="" disabled>Choose the source's license</option>
          {licenses.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <p className="field-help">The catalog accepts open licenses only. Other licenses can't be published yet.</p>
      <label>Attribution
        <textarea required rows={2} value={attribution} onChange={(event) => setAttribution(event.target.value)} placeholder="Course notes by …, University …" />
      </label>
      {request.isError && <p className="error-notice" role="alert">{request.error.message}</p>}
      <button type="submit" className="button button-primary" disabled={request.isPending}>Request publication</button>
    </form>}
  </section>
}
