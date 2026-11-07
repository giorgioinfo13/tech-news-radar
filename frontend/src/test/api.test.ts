import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configureIdentity, mutate, request } from '../api'

beforeEach(() => {
  configureIdentity({ identity: 'reader', token: async () => 'test-token', failure: vi.fn() })
})
afterEach(() => {
  configureIdentity()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

function pendingFetch() {
  const fetch = vi.fn(
    (_url: string, options: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        options.signal!.addEventListener('abort', () => reject(options.signal!.reason))
      }),
  )
  vi.stubGlobal('fetch', fetch)
  return fetch
}

// Browser AbortSignal.timeout uses a platform clock. Drive that clock explicitly
// so these tests verify observable waiting/cancellation without a real 90s sleep.
function controlledTimeout() {
  vi.useFakeTimers()
  vi.spyOn(AbortSignal, 'timeout').mockImplementation((delay) => {
    const controller = new AbortController()
    setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), delay)
    return controller.signal
  })
}

describe('cold start requests', () => {
  it('allows a one-minute wake-up and sends a private authenticated request once', async () => {
    controlledTimeout()
    const fetch = vi.fn(
      (_url: string, options: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          options.signal!.addEventListener('abort', () => reject(options.signal!.reason))
          setTimeout(() => resolve(Response.json({ id: 'reader' })), 60000)
        }),
    )
    vi.stubGlobal('fetch', fetch)
    const result = request('/me')
    await vi.advanceTimersByTimeAsync(60000)
    await expect(result).resolves.toEqual({ id: 'reader' })
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/me')
    expect(new Headers(options.headers).get('Authorization')).toBe('Bearer test-token')
    expect(options.cache).toBe('no-store')
    expect(options.credentials).toBe('omit')
  })
  it('stops after 90 seconds without logging out or retrying a write', async () => {
    controlledTimeout()
    const fetch = pendingFetch()
    const result = expect(mutate('/sources/1/refresh', 'POST')).rejects.toThrow(
      'Esito non confermato',
    )
    await vi.advanceTimersByTimeAsync(90000)
    await result
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('still cancels a sleeping request immediately on logout', async () => {
    const fetch = pendingFetch()
    const result = request('/me')
    await Promise.resolve()
    configureIdentity()
    await expect(result).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('reports a gateway timeout without invalidating the current session', async () => {
    const failure = vi.fn()
    configureIdentity({ identity: 'reader', token: async () => 'test-token', failure })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('Gateway timeout', { status: 504 })),
    )
    await expect(request('/me')).rejects.toThrow('Attendi un minuto')
    expect(failure).not.toHaveBeenCalled()
  })
})
