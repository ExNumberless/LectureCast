import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { AppShell } from './Shell'

const API_ROOT = '/api/auth/browser/v1'

type AuthPage = 'signin' | 'signup'
type AuthStage = 'email' | 'code'
type AuthUser = { email: string; display: string; has_usable_password: boolean }

function csrfCookie(name: string) {
  const cookie = document.cookie.split('; ').find((value) => value.startsWith(`${name}=`))
  return cookie?.slice(cookie.indexOf('=') + 1)
}

async function authRequest(
  path: string,
  body?: Record<string, string>,
  method?: 'GET' | 'POST' | 'DELETE',
  allowPending = false,
) {
  const csrfResponse = await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
  const { csrf_cookie_name: cookieName } = await csrfResponse.json()
  const token = csrfCookie(cookieName)
  const response = await fetch(`${API_ROOT}${path}`, {
    method: method ?? (body ? 'POST' : 'GET'),
    credentials: 'same-origin',
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { 'X-CSRFToken': decodeURIComponent(token) } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok && !(allowPending && response.status === 401)) {
    const errors = payload.errors?.map((item: { message?: string }) => item.message).filter(Boolean)
    throw new Error(errors?.join(' ') || payload.detail || 'Authentication request failed.')
  }
  return payload
}

function App() {
  const page: AuthPage | null = window.location.pathname === '/signup' ? 'signup' : window.location.pathname === '/signin' ? 'signin' : null
  const verificationMatch = window.location.pathname.match(/^\/verify-email\/(.+)$/)
  const verificationKey = verificationMatch?.[1]
  const [stage, setStage] = useState<AuthStage>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionUser, setSessionUser] = useState<AuthUser | null>(null)
  const [sessionLoaded, setSessionLoaded] = useState(false)
  const verificationStarted = useRef(false)

  useEffect(() => {
    let active = true
    async function loadSession() {
      try {
        const response = await fetch(`${API_ROOT}/auth/session`, { credentials: 'same-origin' })
        const payload = await response.json()
        if (active) setSessionUser(payload.meta?.is_authenticated ? payload.data?.user ?? null : null)
      } catch {
        if (active) setError('Could not check your sign-in status.')
      } finally {
        if (active) setSessionLoaded(true)
      }
    }
    void loadSession()
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!verificationKey || verificationStarted.current) return
    verificationStarted.current = true
    authRequest('/auth/email/verify', { key: decodeURIComponent(verificationKey) }, 'POST')
      .then(() => setMessage('Email verified.'))
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Email verification failed.'))
  }, [verificationKey])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    setError('')
    try {
      if (page === 'signup') {
        await authRequest('/auth/signup', { email }, 'POST', true)
        setMessage('Your account is ready. Check your email if verification is required.')
        window.location.assign('/')
      } else if (stage === 'email') {
        await authRequest('/auth/code/request', { email }, undefined, true)
        setStage('code')
        setMessage(`Enter the sign-in code sent to ${email}.`)
      } else {
        await authRequest('/auth/code/confirm', { code }, 'POST')
        window.location.assign('/')
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Authentication request failed.')
    } finally {
      setBusy(false)
    }
  }

  async function resendCode() {
    setBusy(true)
    setError('')
    try {
      await authRequest('/auth/code/resend', undefined, 'POST')
      setMessage(`A new sign-in code was sent to ${email}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not resend the code.')
    } finally {
      setBusy(false)
    }
  }

  async function signOut() {
    setBusy(true)
    setError('')
    try {
      // allauth returns 401 with the signed-out session payload after logout.
      await authRequest('/auth/session', undefined, 'DELETE', true)
      setSessionUser(null)
      window.location.assign('/signin')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not sign out.')
      setBusy(false)
    }
  }

  if (!sessionLoaded && !verificationKey) {
    return <main><h1>LectureCast</h1><p role="status">Checking your sign-in…</p></main>
  }

  if (verificationKey) {
    return <main className="auth-card"><h1>Verify your email</h1>{message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}<a href="/signin">Sign in</a></main>
  }

  if (sessionUser) {
    return <AppShell user={sessionUser} onSignOut={() => { void signOut() }} />
  }

  if (!page) {
    return <main><h1>LectureCast</h1><p>Course websites and materials, turned into narrated slideshows.</p>
      <nav aria-label="Account"><a href="/signin">Sign in</a>{' · '}<a href="/signup">Create an account</a></nav></main>
  }

  return <main className="auth-card">
    <a href="/">LectureCast</a>
    <h1>{page === 'signup' ? 'Create your account' : stage === 'code' ? 'Check your email' : 'Sign in'}</h1>
    <form onSubmit={submit}>
      <label>Email<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} disabled={stage === 'code'} /></label>
      {page === 'signin' && stage === 'code' && <label>Sign-in code<input autoCapitalize="characters" autoComplete="one-time-code" required value={code} onChange={(event) => setCode(event.target.value)} /></label>}
      <button type="submit" disabled={busy}>{busy ? 'Please wait…' : page === 'signup' ? 'Create account' : stage === 'email' ? 'Email me a sign-in code' : 'Sign in'}</button>
    </form>
    {page === 'signin' && stage === 'email' && <a className="google-button" href="/api/auth/google/login/">Continue with Google</a>}
    {page === 'signin' && stage === 'code' && <button className="secondary-button" type="button" onClick={resendCode} disabled={busy}>Resend code</button>}
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    <p>{page === 'signup' ? 'Already registered?' : 'New to LectureCast?'}{' '}
      <a href={page === 'signup' ? '/signin' : '/signup'}>{page === 'signup' ? 'Sign in' : 'Create an account'}</a>
    </p>
  </main>
}

export default App
