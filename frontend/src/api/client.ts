type ApiOptions = Omit<RequestInit, 'body'> & { body?: object | FormData }

function readCookie(name: string) {
  const cookie = document.cookie.split('; ').find((value) => value.startsWith(name + '='))
  return cookie?.slice(cookie.indexOf('=') + 1)
}

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers = new Headers(options.headers)
  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(options.body)
  }
  if (method !== 'GET' && method !== 'HEAD') {
    const csrfResponse = await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
    if (!csrfResponse.ok) throw new Error('Could not prepare a secure request.')
    const { csrf_cookie_name: cookieName } = await csrfResponse.json()
    const token = readCookie(cookieName)
    if (token) headers.set('X-CSRFToken', decodeURIComponent(token))
  }
  const response = await fetch(path, { ...options, method, headers, body, credentials: 'same-origin' })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail ?? Object.values(payload ?? {}).flat().join(' ')
    throw new Error(typeof detail === 'string' && detail ? detail : 'The request could not be completed.')
  }
  return payload as T
}
