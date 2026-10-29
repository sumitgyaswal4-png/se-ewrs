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

/** Where the API lives. In development Vite proxies /api on this origin;
 * a production build served from another host sets VITE_API_BASE_URL to
 * the backend's origin (e.g. https://se-ewrs-api.onrender.com). */
export function apiBaseUrl(origin = import.meta.env.VITE_API_BASE_URL) {
  return origin ? `${origin.replace(/\/+$/, '')}/api` : '/api'
}

export const api = axios.create({
  baseURL: apiBaseUrl(),
  // A free host that has gone to sleep takes about a minute to wake, so a
  // deployment raises this with VITE_API_TIMEOUT_MS.
  timeout: Number(import.meta.env.VITE_API_TIMEOUT_MS) || 30_000,
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
        new ApiError(
          'The request timed out. The server may be waking up; try again in a minute.',
          { status: 0 },
        ),
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
