// Calls to the hub. A 401 sends the person to the sign-in page and back here afterwards.
export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

export async function api(path, { method = 'GET', body } = {}) {
  const r = await fetch(path, {
    method,
    headers: body ? { 'content-type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  })
  if (r.status === 401) {
    location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search)
    throw new ApiError(401, 'sign in first')
  }
  const data = r.headers.get('content-type')?.includes('json') ? await r.json() : await r.text()
  if (!r.ok) throw new ApiError(r.status, data?.detail || String(data))
  return data
}

// Files (multipart form); the same sign-in and error handling as api()
export async function apiForm(path, form) {
  const r = await fetch(path, { method: 'POST', body: form, credentials: 'same-origin' })
  if (r.status === 401) {
    location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search)
    throw new ApiError(401, 'sign in first')
  }
  const data = r.headers.get('content-type')?.includes('json') ? await r.json() : await r.text()
  if (!r.ok) throw new ApiError(r.status, data?.detail || String(data))
  return data
}

export const objectPath = (type, key) => `/o/${encodeURIComponent(type)}/${encodeURIComponent(key)}`
export const apiObject = (type, key) => `/api/ont/objects/${encodeURIComponent(type)}/${encodeURIComponent(key)}`
