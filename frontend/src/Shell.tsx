import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { lazy, Suspense, useState } from 'react'
import type { FormEvent } from 'react'
import type { components } from './api/schema'
import { apiRequest } from './api/client'
import { Link, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router'
import { CoursePage } from './pipeline/CoursePage'

type User = { email: string; display: string }
type SettingProperty = { type?: string; title?: string; description?: string; enum?: (string | number | boolean)[]; items?: { type?: string } }
type CourseCreate = Omit<components['schemas']['Course'], 'id' | 'owner' | 'source_file' | 'visibility' | 'created_at' | 'updated_at'>
// KaTeX and highlight.js load only when a lecture is opened.
const PlayerPage = lazy(() => import('./player/PlayerPage').then((module) => ({ default: module.PlayerPage })))

const providerLabels: Record<components['schemas']['ProviderEnum'], string> = {
  website: 'Course website',
  ocw: 'MIT OpenCourseWare',
  folder: 'Uploaded materials',
}

export function AppShell({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  return <div className="app-shell">
    <aside className="sidebar">
      <Link className="brand sidebar-brand" to="/"><span className="brand-mark">L</span> LectureCast</Link>
      <p className="sidebar-label">WORKSPACE</p>
      <nav className="side-nav" aria-label="Main navigation">
        <NavLink to="/courses" end className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}><span className="nav-icon">▦</span> My courses</NavLink>
        <NavLink to="/courses/new" className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}><span className="nav-icon">＋</span> New course</NavLink>
      </nav>
      <div className="sidebar-bottom"><div className="avatar">{user.display.charAt(0).toUpperCase()}</div><div className="account-copy"><strong>{user.display}</strong><span>Personal workspace</span></div><button className="icon-button" onClick={onSignOut} aria-label="Sign out" title="Sign out">↗</button></div>
    </aside>
    <div className="main-column">
      <header className="topbar"><span className="breadcrumb">Workspace <span>/</span> Courses</span><span className="topbar-user">{user.email}</span></header>
      <Suspense fallback={<p className="query-message" role="status">Loading…</p>}><Routes>
        <Route path="/" element={<Navigate to="/courses" replace />} />
        <Route path="/courses" element={<MyCourses />} />
        <Route path="/courses/new" element={<NewCourse />} />
        <Route path="/courses/:courseId" element={<CoursePage />} />
        <Route path="/courses/:courseId/lectures/:lectureNumber" element={<PlayerPage />} />
        <Route path="/courses/:courseId/lectures/:lectureNumber/slides/:slide" element={<PlayerPage />} />
        <Route path="*" element={<Navigate to="/courses" replace />} />
      </Routes></Suspense>
    </div>
  </div>
}

function MyCourses() {
  const coursesQuery = useQuery({
    queryKey: ['courses'],
    queryFn: () => apiRequest<components['schemas']['Course'][]>('/api/courses/'),
  })
  const courses = coursesQuery.data ?? []
  return <main className="page-content">
    <div className="page-header"><div><p className="eyebrow">YOUR WORKSPACE</p><h1>My courses</h1><p className="page-description">Manage your courses and follow their journey from source material to finished lessons.</p></div><Link className="button button-primary" to="/courses/new">＋ New course</Link></div>
    {coursesQuery.isPending && <p className="query-message" role="status">Loading your courses…</p>}
    {coursesQuery.isError && <p className="error-notice" role="alert">{coursesQuery.error.message}</p>}
    {!coursesQuery.isPending && !coursesQuery.isError && courses.length === 0 && <section className="empty-state">
      <div className="empty-illustration" aria-hidden="true"><div className="book book-back"/><div className="book book-front"><span>✦</span></div><div className="spark spark-a">✳</div><div className="spark spark-b">✦</div></div>
      <p className="eyebrow">A FRESH START</p><h2>Your course library is ready</h2><p>Your courses will show up here. Add a course to start building your first narrated lesson.</p><Link className="button button-primary" to="/courses/new">Set up a course →</Link>
    </section>}
    {courses.length > 0 && <section className="course-list" aria-label="Your courses">{courses.map((course) => <article className="course-row" key={course.id}><div className="course-cover">{course.title.charAt(0).toUpperCase()}</div><div className="course-row-copy"><h2><Link to={`/courses/${course.id}`}>{course.title}</Link></h2><p>{providerLabels[course.provider]} · Added {new Date(course.created_at).toLocaleDateString()}</p></div><span className="course-visibility">Private</span></article>)}</section>}
  </main>
}

function NewCourse() {
  const [providerId, setProviderId] = useState('website')
  const [title, setTitle] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const [providerSettings, setProviderSettings] = useState<Record<string, unknown>>({})
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const providersQuery = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiRequest<components['schemas']['Provider'][]>('/api/providers'),
  })
  const providers = providersQuery.data ?? []
  const provider = providers.find((item) => item.id === providerId) ?? providers[0]
  const createCourse = useMutation({
    mutationFn: async () => {
      if (!provider) throw new Error('No course sources are enabled.')
      if (provider.source_kind === 'upload') {
        if (!sourceFile) throw new Error('Choose a ZIP archive to upload.')
        const signed = await apiRequest<components['schemas']['UploadUrlResponse']>(
          '/api/courses/upload-url', { method: 'POST', body: { provider: provider.id, filename: sourceFile.name } },
        )
        const form = new FormData()
        for (const [key, value] of Object.entries(signed.fields)) form.set(key, value)
        form.set('Content-Type', 'application/zip')
        form.set('file', sourceFile)
        const upload = await fetch(signed.url, { method: 'POST', body: form })
        if (!upload.ok) throw new Error('The ZIP archive could not be uploaded.')
        const requestBody: CourseCreate = {
          title,
          provider: provider.id as CourseCreate['provider'],
          source_upload: signed.key,
          settings: providerSettings,
        }
        return apiRequest<components['schemas']['Course']>('/api/courses/', {
          method: 'POST', body: requestBody,
        })
      }
      const requestBody: CourseCreate = {
        title,
        provider: provider.id as CourseCreate['provider'],
        source_url: sourceUrl,
        settings: providerSettings,
      }
      return apiRequest<components['schemas']['Course']>('/api/courses/', {
        method: 'POST', body: requestBody,
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
      navigate('/courses')
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    createCourse.mutate()
  }

  function updateProviderSetting(key: string, value: unknown) {
    setProviderSettings((current) => ({ ...current, [key]: value }))
  }

  const settingProperties = (provider?.settings_schema as { properties?: Record<string, SettingProperty> } | undefined)?.properties ?? {}

  return <main className="page-content page-content-narrow">
    <div className="page-header"><div><p className="eyebrow">GET STARTED</p><h1>Add a course</h1><p className="page-description">Choose where your course materials live. You can review everything before processing begins.</p></div></div>
    <form className="course-form" onSubmit={submit}>
      <fieldset disabled={providersQuery.isPending || providers.length === 0}><legend>Choose a source</legend><div className="provider-grid">
        {providers.map((item) => <Provider key={item.id} id={item.id} selected={provider?.id ?? providerId} change={(id) => { setProviderId(id); setProviderSettings({}); setSourceFile(null) }} icon={item.source_kind === 'upload' ? '↑' : item.id === 'ocw' ? '▤' : '⌘'} title={item.name} detail={item.description}/>)}
      </div></fieldset>
      {providersQuery.isPending && <p className="query-message" role="status">Loading available course sources…</p>}
      {providersQuery.isError && <p className="error-notice" role="alert">{providersQuery.error.message}</p>}
      {providers.length > 0 && <div className="form-fields">
        <label>Course name<input type="text" placeholder="e.g. Introduction to Biology" required value={title} onChange={(event) => setTitle(event.target.value)}/><span className="field-help">The name used to identify this course in your library.</span></label>
        {provider?.source_kind === 'upload' ? <label>Course archive (.zip)<input type="file" accept=".zip,application/zip" required onChange={(event) => setSourceFile(event.target.files?.[0] ?? null)}/><span className="field-help">Choose the ZIP export or archive that contains the course materials.</span></label> : <label>Course website URL<input type="url" placeholder="https://example.edu/course" required value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)}/><span className="field-help">Paste the public course homepage or schedule page where LectureCast can find the materials.</span></label>}
        {Object.entries(settingProperties).map(([key, property]) => <label key={key}>{property.title ?? key.replaceAll('_', ' ')}
          {property.enum ? <select value={String(providerSettings[key] ?? '')} onChange={(event) => updateProviderSetting(key, event.target.value)}><option value="">Select…</option>{property.enum.map((value) => <option key={String(value)} value={String(value)}>{String(value)}</option>)}</select>
            : property.type === 'array' ? <input type="text" value={Array.isArray(providerSettings[key]) ? (providerSettings[key] as string[]).join(', ') : ''} onChange={(event) => updateProviderSetting(key, event.target.value.split(',').map((value) => value.trim()).filter(Boolean))} placeholder="e.g. lecture, textbook|reading, discussion"/>
              : <input type="text" value={String(providerSettings[key] ?? '')} onChange={(event) => updateProviderSetting(key, event.target.value)}/>}{property.description && <span className="field-help">{property.description}</span>}</label>)}
      </div>}
      {createCourse.isError && <p className="error-notice" role="alert">{createCourse.error.message}</p>}
      <div className="form-actions"><Link className="button button-subtle" to="/courses">Cancel</Link><button className="button button-primary" type="submit" disabled={createCourse.isPending || !provider}>{createCourse.isPending ? 'Creating…' : 'Create course →'}</button></div>
    </form>
  </main>
}

function Provider({ id, selected, change, icon, title, detail }: { id: string; selected: string; change: (id: string) => void; icon: string; title: string; detail: string }) {
  return <button type="button" className={'provider-card' + (selected === id ? ' selected' : '')} onClick={() => change(id)} aria-pressed={selected === id}><span className="provider-icon">{icon}</span><strong>{title}</strong><span>{detail}</span><span className="provider-check">{selected === id ? '✓' : ''}</span></button>
}
