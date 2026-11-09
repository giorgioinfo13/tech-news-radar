import { message, type UiMessage } from './messages'
import type { Session } from '@supabase/supabase-js'
import { ApiError, configureIdentity, request, type AppUser } from './api'
import { completeCallback, type AuthConfiguration } from './auth-client'

export type AuthState = {
  status: 'loading' | 'signed-out' | 'denied' | 'error' | 'ready' | 'unconfigured'
  user?: AppUser
  message?: UiMessage
}

export class AuthController {
  private state: AuthState = { status: 'loading' }
  private listeners = new Set<() => void>()
  private epoch = 0
  private validation = 0
  private identity: string | null = null
  private running = false
  private terminating = false
  private unsubscribe?: () => void
  constructor(readonly configuration: AuthConfiguration) {}
  snapshot = () => this.state
  subscribe = (callback: () => void) => {
    this.listeners.add(callback)
    return () => {
      this.listeners.delete(callback)
    }
  }
  private publish(state: AuthState) {
    this.state = state
    this.listeners.forEach((callback) => callback())
  }
  private fail = (status: number) => {
    if (status === 403) {
      void this.validate()
      return
    }
    this.identity = null
    this.terminating = true
    this.validation++
    configureIdentity()
    this.publish({
      status: 'signed-out',
      message: message('Your session has expired. Sign in again.'),
    })
    void this.configuration.client?.auth.signOut({ scope: 'local' }).catch(() => {})
  }
  private receive(session: Session | null) {
    if (!this.running || (this.terminating && session)) return
    if (!session) this.terminating = false
    const next = session?.user.id ?? null
    if (next !== this.identity || !next) {
      this.identity = next
      this.validation++
      configureIdentity()
      this.publish({
        status: next ? 'loading' : 'signed-out',
        message: !next && this.state.status === 'signed-out' ? this.state.message : undefined,
      })
    }
    if (!next) return
    const client = this.configuration.client!
    configureIdentity({
      identity: next,
      token: async () => {
        const { data, error } = await client.auth.getSession()
        if (error) throw new Error('Session unavailable')
        return data.session?.user.id === next ? data.session.access_token : null
      },
      failure: this.fail,
    })
    void this.validate()
  }
  async validate() {
    const version = ++this.validation
    try {
      const user = await request<AppUser>('/me')
      if (version === this.validation && this.running) this.publish({ status: 'ready', user })
    } catch (error) {
      if (version !== this.validation || !this.running) return
      this.publish({
        status: error instanceof ApiError && error.status === 403 ? 'denied' : 'error',
        message:
          error instanceof ApiError
            ? error.uiMessage
            : message('Unable to verify access. Try again.'),
      })
    }
  }
  start = () => {
    this.running = true
    const epoch = ++this.epoch
    const { mode, client } = this.configuration
    configureIdentity()
    if (mode === 'unconfigured') this.publish({ status: 'unconfigured' })
    else if (mode === 'local') {
      configureIdentity({ identity: 'local', token: async () => null, failure: this.fail })
      void this.validate()
    } else if (client) {
      let initialized = false
      const { data } = client.auth.onAuthStateChange((_event, session) => {
        // Keep the SDK callback synchronous. Session API calls run after its lock is released.
        if (initialized)
          queueMicrotask(() => {
            if (epoch === this.epoch) this.receive(session)
          })
      })
      this.unsubscribe = () => data.subscription.unsubscribe()
      void (async () => {
        try {
          await completeCallback(client)
          const { data, error } = await client.auth.getSession()
          if (epoch !== this.epoch) return
          if (error) throw new Error('Unable to restore session')
          initialized = true
          this.receive(data.session)
        } catch {
          if (epoch === this.epoch) {
            initialized = true
            this.publish({
              status: 'error',
              message: message('Sign-in failed or your session expired. Try again.'),
            })
          }
        }
      })()
    }
    return () => {
      this.running = false
      this.epoch++
      this.validation++
      this.unsubscribe?.()
      configureIdentity()
    }
  }
  retry = () => {
    if (this.identity || this.configuration.mode === 'local') void this.validate()
    else {
      this.unsubscribe?.()
      this.start()
    }
  }
  login = async () => {
    this.terminating = false
    const client = this.configuration.client
    if (!client) return
    try {
      const { error } = await client.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${location.origin}${location.pathname}`,
          queryParams: { prompt: 'select_account' },
        },
      })
      if (error) throw error
    } catch {
      this.publish({
        status: 'signed-out',
        message: message('Sign-in failed. Check your connection and try again.'),
      })
    }
  }
  logout = async () => {
    this.terminating = true
    this.validation++
    this.identity = null
    configureIdentity()
    this.publish({ status: 'signed-out' })
    try {
      const result = await this.configuration.client?.auth.signOut({ scope: 'local' })
      if (result?.error) throw result.error
    } catch {
      if (!this.running || this.identity || this.state.status !== 'signed-out') return
      this.publish({
        status: 'signed-out',
        message: message(
          'You have signed out of this browser. Remote session sign-out could not be confirmed.',
        ),
      })
    }
  }
}
