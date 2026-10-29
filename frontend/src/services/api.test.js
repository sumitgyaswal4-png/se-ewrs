/** The response interceptor: how API failures reach the pages. */

import { AxiosError } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api, apiBaseUrl, setUnauthorisedHandler } from './api.js'

/** An adapter that answers every request with the given status and body. */
function respondWith(status, data, headers = {}) {
  return (config) =>
    Promise.reject(
      new AxiosError(`Request failed with status code ${status}`, 'ERR_BAD_REQUEST', config, null, {
        status,
        data,
        headers,
        config,
      }),
    )
}

afterEach(() => setUnauthorisedHandler(null))

describe('API error handling', () => {
  it('turns a throttled sign-in into a readable error and keeps the user on the page', async () => {
    const onUnauthorised = vi.fn()
    setUnauthorisedHandler(onUnauthorised)
    const detail = 'Too many failed sign-in attempts. Try again in 15 minutes.'

    const failure = api.post(
      '/auth/login',
      { email: 'a@b.edu', password: 'x' },
      { adapter: respondWith(429, { detail, error_code: 'too_many_requests' }, { 'retry-after': '900' }) },
    )

    await expect(failure).rejects.toBeInstanceOf(ApiError)
    await expect(failure).rejects.toMatchObject({
      message: detail,
      status: 429,
      code: 'too_many_requests',
    })
    expect(onUnauthorised).not.toHaveBeenCalled()
  })

  it('signs the user out on a 401 from any endpoint but the sign-in itself', async () => {
    const onUnauthorised = vi.fn()
    setUnauthorisedHandler(onUnauthorised)
    const expired = respondWith(401, { detail: 'Token expired', error_code: 'unauthenticated' })

    await expect(api.post('/auth/login', {}, { adapter: expired })).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorised).not.toHaveBeenCalled()

    await expect(api.get('/students', { adapter: expired })).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorised).toHaveBeenCalledTimes(1)
  })
})

describe('API base URL', () => {
  it('uses the dev-server proxy when no backend origin is configured', () => {
    expect(apiBaseUrl(undefined)).toBe('/api')
    expect(apiBaseUrl('')).toBe('/api')
  })

  it("points at the deployed backend's /api, however the origin is written", () => {
    expect(apiBaseUrl('https://se-ewrs-api.onrender.com')).toBe('https://se-ewrs-api.onrender.com/api')
    expect(apiBaseUrl('https://se-ewrs-api.onrender.com/')).toBe('https://se-ewrs-api.onrender.com/api')
  })
})
