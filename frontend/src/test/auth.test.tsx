import { StrictMode } from 'react'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { AuthChangeEvent, Session, SupabaseClient } from '@supabase/supabase-js'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthController } from '../auth'
import { authConfiguration } from '../auth-client'
import { request } from '../api'
import { mockServer, source } from './server'

function session(id = 'alice', token = `${id}-token`): Session {
  return {
    access_token: token,
    refresh_token: 'test-refresh',
    token_type: 'bearer',
    expires_in: 3600,
    user: {
      id,
      user_metadata: { role: 'admin' },
      app_metadata: {},
      aud: 'authenticated',
      created_at: '2026-01-01T00:00:00Z',
    },
  } as Session
}
function sdk(initial: Session | null = null) {
  let current = initial
  const listeners = new Set<(event: AuthChangeEvent, session: Session | null) => void>()
  const emit = (event: AuthChangeEvent, value: Session | null) => {
    current = value
    listeners.forEach((callback) => callback(event, value))
  }
  const auth = {
    getSession: vi.fn(async () => ({ data: { session: current }, error: null })),
    onAuthStateChange: vi.fn(
      (callback: (event: AuthChangeEvent, session: Session | null) => void) => {
        listeners.add(callback)
        return { data: { subscription: { unsubscribe: () => listeners.delete(callback) } } }
      },
    ),
    exchangeCodeForSession: vi.fn(async () => {
      emit('SIGNED_IN', session())
      return { data: { session: current }, error: null }
    }),
    signInWithOAuth: vi.fn(async () => ({
      data: { url: 'https://example.supabase.co/auth/v1/authorize' },
      error: null,
    })),
    signOut: vi.fn(async () => {
      emit('SIGNED_OUT', null)
      return { error: null }
    }),
  }
  const client = { auth } as unknown as SupabaseClient
  const controller = new AuthController({ mode: 'supabase', client })
  return { auth, controller, emit }
}
function open(controller: AuthController) {
  return render(
    <StrictMode>
      <App controller={controller} />
    </StrictMode>,
  )
}

describe('session and access', () => {
  it('waits for login without fetching personal data, then starts Google OAuth', async () => {
    const { calls } = mockServer()
    const { controller, auth } = sdk()
    open(controller)
    await userEvent.click(await screen.findByRole('button', { name: 'Accedi con Google' }))
    expect(calls).toHaveLength(0)
    expect(auth.signInWithOAuth).toHaveBeenCalledWith({
      provider: 'google',
      options: {
        redirectTo: `${location.origin}/`,
        queryParams: { prompt: 'select_account' },
      },
    })
  })
  it('starts Google OAuth from the account menu without fetching personal data', async () => {
    const { calls } = mockServer()
    const { controller, auth } = sdk()
    open(controller)
    await screen.findByRole('heading', { name: 'Un posto per le tue notizie.' })
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    const menu = screen.getByRole('region', { name: 'Account e tema' })
    await userEvent.click(within(menu).getByRole('button', { name: 'Accedi con Google' }))
    expect(auth.signInWithOAuth).toHaveBeenCalledOnce()
    expect(calls).toHaveLength(0)
  })
  it('restores a reader session, sends its bearer token and hides administrative controls', async () => {
    const { state, calls } = mockServer()
    state.user = { id: 'alice-app', display_name: 'Alice', role: 'reader' }
    const { controller } = sdk(session())
    history.replaceState(null, '', '/#categories')
    open(controller)
    await screen.findByRole('heading', { name: 'Notizie' })
    expect(screen.queryByRole('link', { name: 'Catalogo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Categorie' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aggiungi fonte' })).not.toBeInTheDocument()
    expect(calls.every((call) => call.authorization === 'Bearer alice-token')).toBe(true)
  })
  it('exchanges a PKCE callback once in StrictMode and removes it from browser history', async () => {
    mockServer()
    history.replaceState(null, '', '/?code=single-use-code#ignored')
    const { controller, auth } = sdk()
    open(controller)
    await screen.findByRole('heading', { name: 'Notizie' })
    expect(auth.exchangeCodeForSession).toHaveBeenCalledExactlyOnceWith('single-use-code')
    expect(location.search).toBe('')
    expect(location.hash).toBe('#news')
  })
  it('shows a safe OAuth cancellation message without displaying provider diagnostics', async () => {
    const { calls } = mockServer()
    history.replaceState(null, '', '/?error=access_denied&error_description=private-secret')
    const { controller, auth } = sdk()
    open(controller)
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private-secret')
    expect(location.search).toBe('')
    expect(auth.exchangeCodeForSession).not.toHaveBeenCalled()
    expect(calls).toHaveLength(0)
  })
  it('recovers from a failed callback without reusing its single-use code', async () => {
    const { calls } = mockServer()
    history.replaceState(null, '', '/?code=expired-code')
    const { controller, auth } = sdk()
    auth.exchangeCodeForSession.mockRejectedValue(new Error('private-provider-error'))
    open(controller)
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private-provider-error')
    await userEvent.click(screen.getByRole('button', { name: 'Riprova' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Accedi con Google' }))
    expect(auth.exchangeCodeForSession).toHaveBeenCalledExactlyOnceWith('expired-code')
    expect(auth.signInWithOAuth).toHaveBeenCalledOnce()
    expect(calls).toHaveLength(0)
  })
  it('keeps unapproved users out and retries approval without creating profiles', async () => {
    const { state, calls } = mockServer()
    state.accessStatus = 403
    const { controller } = sdk(session())
    open(controller)
    await screen.findByRole('heading', { name: 'Accesso riservato' })
    expect(calls.every((call) => call.path === '/api/me')).toBe(true)
    state.accessStatus = 200
    await userEvent.click(screen.getByRole('button', { name: 'Verifica di nuovo' }))
    await screen.findByRole('heading', { name: 'Notizie' })
  })
  it('clears data on logout and does not restore it from late responses', async () => {
    const server = mockServer()
    const { controller, auth } = sdk(session())
    open(controller)
    await screen.findByRole('link', { name: /Una nuova idea/ })
    let complete!: (response: Response) => void
    server.fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve
        }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Da leggere' }))
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await userEvent.click(screen.getByRole('button', { name: 'Esci' }))
    await screen.findByRole('button', { name: 'Accedi con Google' })
    await act(async () =>
      complete(server.response({ items: server.state.articles, total: 1, limit: 20, offset: 0 })),
    )
    expect(screen.queryByRole('link', { name: /Una nuova idea/ })).not.toBeInTheDocument()
    expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  })
  it('updates tokens without losing filters, then clears data when the account changes', async () => {
    const { state, calls } = mockServer()
    const { controller, emit } = sdk(session())
    state.user = { id: 'alice-app', display_name: 'Alice', role: 'reader' }
    open(controller)
    await screen.findByRole('link', { name: /Una nuova idea/ })
    await userEvent.type(screen.getByLabelText('Cerca nelle notizie'), 'kept draft')
    await act(async () => emit('TOKEN_REFRESHED', session('alice', 'new-token')))
    await waitFor(() => expect(calls.at(-1)?.authorization).toBe('Bearer new-token'))
    expect(screen.getByLabelText('Cerca nelle notizie')).toHaveValue('kept draft')
    state.user = { id: 'bob-app', display_name: 'Bob', role: 'reader' }
    state.subscriptions = []
    await act(async () => emit('SIGNED_IN', session('bob')))
    await screen.findByRole('heading', { name: 'Scegli da dove iniziare' })
    expect(screen.queryByRole('link', { name: /Una nuova idea/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })
  it('expires a rejected session and hides data after access is revoked', async () => {
    const { state } = mockServer()
    const { controller } = sdk(session())
    open(controller)
    await screen.findByRole('link', { name: /Una nuova idea/ })
    state.accessStatus = 401
    await userEvent.click(screen.getByRole('button', { name: 'Da leggere' }))
    await screen.findByRole('button', { name: 'Accedi con Google' })
    expect(screen.queryByRole('heading', { name: 'Notizie' })).not.toBeInTheDocument()
  })
  it('rechecks authorization after a forbidden API response', async () => {
    const { state } = mockServer()
    const { controller } = sdk(session())
    open(controller)
    await screen.findByRole('link', { name: /Una nuova idea/ })
    state.accessStatus = 403
    await userEvent.click(screen.getByRole('button', { name: 'Da leggere' }))
    await screen.findByRole('heading', { name: 'Accesso riservato' })
    expect(screen.queryByRole('link', { name: /Una nuova idea/ })).not.toBeInTheDocument()
  })
  it('reports a network failure during session restoration and can retry', async () => {
    mockServer()
    const { controller, auth } = sdk(session())
    auth.getSession.mockRejectedValue(new Error('private diagnostic'))
    open(controller)
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private diagnostic')
    auth.getSession.mockResolvedValue({ data: { session: session() }, error: null })
    await userEvent.click(screen.getByRole('button', { name: 'Riprova' }))
    await screen.findByRole('heading', { name: 'Notizie' })
  })
  it('keeps logout local when remote session revocation fails', async () => {
    mockServer()
    const { controller, auth, emit } = sdk(session())
    auth.signOut.mockImplementationOnce(async () => {
      emit('SIGNED_OUT', null)
      throw new Error('offline')
    })
    open(controller)
    await screen.findByRole('link', { name: /Una nuova idea/ })
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await userEvent.click(screen.getByRole('button', { name: 'Esci' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('chiusura della sessione remota')
    expect(screen.queryByRole('heading', { name: 'Notizie' })).not.toBeInTheDocument()
  })
  it('ignores a late logout failure after another account signs in', async () => {
    const { state } = mockServer()
    const { controller, auth, emit } = sdk(session())
    let rejectLogout!: (error: Error) => void
    auth.signOut.mockImplementationOnce(() => {
      emit('SIGNED_OUT', null)
      return new Promise((_resolve, reject) => {
        rejectLogout = reject
      })
    })
    open(controller)
    await screen.findByRole('heading', { name: 'Notizie' })
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await userEvent.click(screen.getByRole('button', { name: 'Esci' }))
    await screen.findByRole('button', { name: 'Accedi con Google' })
    state.user = { id: 'bob-app', display_name: 'Bob', role: 'reader' }
    await act(async () => emit('SIGNED_IN', session('bob')))
    await screen.findByRole('heading', { name: 'Notizie' })
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await screen.findByText('Bob')
    await act(async () => rejectLogout(new Error('offline')))
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Accedi con Google' })).not.toBeInTheDocument()
  })
})

describe('personal sources', () => {
  it('confirms initial choices, tolerates partial saves and does not follow unchecked sources', async () => {
    const { state, calls } = mockServer()
    state.subscriptions = []
    state.sources.push(
      { ...source, id: 2, name: 'Second source' },
      { ...source, id: 3, name: 'Third source' },
    )
    state.failSubscription = 2
    const { controller } = sdk(session())
    open(controller)
    await userEvent.click(await screen.findByRole('checkbox', { name: /Third source/ }))
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Segui 2 fonti e continua' }))
    await screen.findByRole('alert')
    expect(state.subscriptions).toEqual([1])
    state.failSubscription = 0
    await userEvent.click(screen.getByRole('button', { name: 'Segui 2 fonti e continua' }))
    await screen.findByRole('heading', { name: 'Notizie' })
    expect(state.subscriptions).toEqual([1, 2])
  })
  it('preserves existing choices, supports unfollowing all sources and keeps read status', async () => {
    const { state, calls } = mockServer()
    state.articles[0].is_read = true
    state.user.role = 'reader'
    const { controller } = sdk(session())
    open(controller)
    await screen.findByRole('link', { name: /Una nuova idea/ })
    expect(
      screen.queryByRole('heading', { name: 'Scegli da dove iniziare' }),
    ).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: 'Le mie fonti' }))
    await userEvent.click(
      await screen.findByRole('button', { name: 'Non seguire più Example News' }),
    )
    await screen.findByRole('button', { name: 'Segui Example News' })
    expect(state.subscriptions).toEqual([])
    expect(state.articles[0].is_read).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Segui Example News' }))
    await screen.findByRole('button', { name: 'Non seguire più Example News' })
    expect(
      calls
        .filter((call) => call.method === 'PUT' || call.method === 'DELETE')
        .every((call) => call.path.startsWith('/api/subscriptions/')),
    ).toBe(true)
  })
  it('does not continue a batch under another user after logout', async () => {
    const server = mockServer()
    server.state.subscriptions = []
    server.state.sources.push({ ...source, id: 2, name: 'Second source' })
    const { controller, emit } = sdk(session())
    open(controller)
    await screen.findByRole('heading', { name: 'Scegli da dove iniziare' })
    let complete!: (response: Response) => void
    server.fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve
        }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Segui 2 fonti e continua' }))
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await userEvent.click(screen.getByRole('button', { name: 'Esci' }))
    server.state.user.id = 'bob-app'
    await act(async () => emit('SIGNED_IN', session('bob')))
    await screen.findByRole('heading', { name: 'Scegli da dove iniziare' })
    await act(async () => complete(server.response(null, 204)))
    expect(server.calls.filter((call) => call.method === 'PUT')).toHaveLength(0)
    // The suspended first fetch bypasses the mock's recording. No second PUT may start.
  })
  it('never overwrites the Authorization header and rejects requests after logout', async () => {
    const server = mockServer()
    const { controller } = sdk(session())
    open(controller)
    await screen.findByRole('heading', { name: 'Notizie' })
    await request('/me', { headers: { Authorization: 'Bearer attacker' } })
    expect(server.calls.at(-1)?.authorization).toBe('Bearer alice-token')
    await act(async () => controller.logout())
    await expect(request('/me')).rejects.toMatchObject({ status: 401 })
  })
})

it('disables local identity in production and rejects privileged frontend keys', () => {
  vi.stubEnv('DEV', false)
  expect(authConfiguration().mode).toBe('unconfigured')
  vi.stubEnv('VITE_LOCAL_MODE', 'false')
  vi.stubEnv('VITE_SUPABASE_URL', 'https://example.supabase.co')
  vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'sb_secret_not-a-public-key')
  expect(authConfiguration().mode).toBe('unconfigured')
})
