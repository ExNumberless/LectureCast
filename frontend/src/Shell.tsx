import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import type { components } from './api/schema'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router'

type User = { email: string; display: string }

function HealthStatus() {
  const query = useQuery<components['schemas']['HealthResponse']>({
    queryKey: ['api-health'],
    queryFn: async () => {
      const response = await fetch('/api/health', { credentials: 'same-origin' })
      if (!response.ok) throw new Error('API unavailable')
      return response.json() as Promise<components['schemas']['HealthResponse']>
    },
  })
  return <p className="api-status" role="status">{query.isPending ? 'Connecting to LectureCast…' : query.isError ? 'Course services are coming online.' : 'LectureCast services are connected.'}</p>
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
      <Routes>
        <Route path="/" element={<Navigate to="/courses" replace />} />
        <Route path="/courses" element={<MyCourses />} />
        <Route path="/courses/new" element={<NewCourse />} />
        <Route path="*" element={<Navigate to="/courses" replace />} />
      </Routes>
    </div>
  </div>
}

function MyCourses() {
  return <main className="page-content">
    <div className="page-header"><div><p className="eyebrow">YOUR WORKSPACE</p><h1>My courses</h1><p className="page-description">Manage your courses and follow their journey from source material to finished lessons.</p></div><Link className="button button-primary" to="/courses/new">＋ New course</Link></div>
    <section className="empty-state">
      <div className="empty-illustration" aria-hidden="true"><div className="book book-back"/><div className="book book-front"><span>✦</span></div><div className="spark spark-a">✳</div><div className="spark spark-b">✦</div></div>
      <p className="eyebrow">A FRESH START</p><h2>Your course library is ready</h2><p>Your courses will show up here. Add a course to start building your first narrated lesson.</p><Link className="button button-primary" to="/courses/new">Set up a course →</Link>
    </section>
    <HealthStatus />
  </main>
}

function NewCourse() {
  const [provider, setProvider] = useState('course-site')
  return <main className="page-content page-content-narrow">
    <div className="page-header"><div><p className="eyebrow">GET STARTED</p><h1>Add a course</h1><p className="page-description">Choose where your course materials live. You can review everything before processing begins.</p></div></div>
    <form className="course-form" onSubmit={(event) => event.preventDefault()}>
      <fieldset><legend>Choose a source</legend><div className="provider-grid">
        <Provider id="course-site" selected={provider} change={setProvider} icon="⌘" title="Course website" detail="Use a public course page"/>
        <Provider id="ocw" selected={provider} change={setProvider} icon="▤" title="OpenCourseWare" detail="Import an OCW course"/>
        <Provider id="upload" selected={provider} change={setProvider} icon="↑" title="Upload materials" detail="Add files from your device"/>
      </div></fieldset>
      <div className="form-fields"><label>Course name<input type="text" placeholder="e.g. Introduction to Biology" disabled/></label>{provider === 'upload' ? <label>Course files<input type="file" multiple disabled/></label> : <label>Course URL<input type="url" placeholder="https://example.edu/course" disabled/></label>}</div>
      <div className="coming-soon"><span className="coming-icon">✦</span><div><strong>Course setup is the next step</strong><p>The courses API and provider integrations are still being built. Source details will be available here when they’re ready.</p></div></div>
      <div className="form-actions"><Link className="button button-subtle" to="/courses">Cancel</Link><button className="button button-primary" type="submit" disabled>Continue →</button></div>
    </form>
  </main>
}

function Provider({ id, selected, change, icon, title, detail }: { id: string; selected: string; change: (id: string) => void; icon: string; title: string; detail: string }) {
  return <button type="button" className={'provider-card' + (selected === id ? ' selected' : '')} onClick={() => change(id)} aria-pressed={selected === id}><span className="provider-icon">{icon}</span><strong>{title}</strong><span>{detail}</span><span className="provider-check">{selected === id ? '✓' : ''}</span></button>
}
