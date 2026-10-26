/** Axios instance shared by every request.
 *
 * Requests attach the stored JWT; responses are unwrapped to `data` and
 * errors are normalised into an `ApiError` carrying the backend's own
 * message, so pages can render a real explanation instead of "something
 * went wrong".
 */

import axios from 'axios'

const TOKEN_KEY = 'se-ewrs.token'
const USER_KEY = 'se-ewrs.user'

export const tokenStore = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set: (token) => {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      /* private browsing: the session simply does not persist */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    } catch {
      /* nothing to clear */
    }
  },
}

export const userStore = {
  get: () => {
    try {
      const raw = localStorage.getItem(USER_KEY)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  },
  set: (user) => {
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    } catch {
      /* ignore */
    }
  },
}

export class ApiError extends Error {
  constructor(message, { status, code, problems } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.problems = problems ?? []
  }
}

export const api = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** Called by the auth provider so a 401 can bounce the user to sign-in. */
let onUnauthorised = null
export function setUnauthorisedHandler(handler) {
  onUnauthorised = handler
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(
        new ApiError('The request timed out. Is the backend still running?', { status: 0 }),
      )
    }
    if (!error.response) {
      return Promise.reject(
        new ApiError(
          'Could not reach the API. Check that the backend is running on port 8000.',
          { status: 0 },
        ),
      )
    }

    const { status, data } = error.response
    const detail =
      (typeof data?.detail === 'string' && data.detail) ||
      (Array.isArray(data?.detail) && data.detail[0]?.msg) ||
      'The request could not be completed.'

    if (status === 401) {
      // Let the sign-in request itself report its own error.
      const isLogin = error.config?.url?.includes('/auth/login')
      if (!isLogin && onUnauthorised) onUnauthorised()
    }

    return Promise.reject(
      new ApiError(detail, { status, code: data?.error_code, problems: data?.problems }),
    )
  },
)

/** Unwraps `response.data` so callers deal in plain payloads. */
export async function request(config) {
  const response = await api.request(config)
  return response.data
}

export const get = (url, params) => request({ method: 'get', url, params })
export const post = (url, data) => request({ method: 'post', url, data })
export const put = (url, data) => request({ method: 'put', url, data })
export const patch = (url, data) => request({ method: 'patch', url, data })
export const del = (url) => request({ method: 'delete', url })

/** Triggers a browser download for a CSV export endpoint. */
export async function downloadCsv(url, params, filename) {
  const response = await api.request({ method: 'get', url, params, responseType: 'blob' })
  const blobUrl = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(blobUrl)
}
