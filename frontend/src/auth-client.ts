import { createClient, type SupabaseClient } from '@supabase/supabase-js'

export type AuthMode = 'local' | 'supabase' | 'unconfigured'
export interface AuthConfiguration {
  mode: AuthMode
  client?: SupabaseClient
}
let client: SupabaseClient | undefined

export function authConfiguration(): AuthConfiguration {
  const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
  const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined
  const local = import.meta.env.VITE_LOCAL_MODE === 'true'
  if (local) {
    return {
      mode:
        import.meta.env.DEV &&
        ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname) &&
        !url &&
        !key
          ? 'local'
          : 'unconfigured',
    }
  }
  try {
    const origin = new URL(url ?? '')
    if (
      origin.protocol !== 'https:' ||
      origin.username ||
      origin.password ||
      origin.search ||
      origin.hash ||
      !['', '/'].includes(origin.pathname) ||
      (origin.port && origin.port !== '443') ||
      !key?.startsWith('sb_publishable_')
    )
      return { mode: 'unconfigured' }
    client ??= createClient(origin.origin, key, {
      auth: {
        flowType: 'pkce',
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    })
    return { mode: 'supabase', client }
  } catch {
    return { mode: 'unconfigured' }
  }
}

// StrictMode can restart effects. Exchange a single-use callback code only once.
const callbacks = new WeakMap<SupabaseClient, Promise<void>>()
export function completeCallback(client: SupabaseClient): Promise<void> {
  const existing = callbacks.get(client)
  if (existing) return existing
  const url = new URL(location.href)
  const hash = new URLSearchParams(url.hash.slice(1))
  const code = url.searchParams.get('code')
  const failed = url.searchParams.has('error') || hash.has('error') || hash.has('access_token')
  if (!code && !failed) return Promise.resolve()
  // Do not leave OAuth credentials or provider diagnostics in history/referrers.
  history.replaceState(null, '', `${url.pathname}#news`)
  const pending = (async () => {
    if (failed) throw new Error('Accesso annullato o non riuscito. Riprova con Google.')
    const { error } = await client.auth.exchangeCodeForSession(code!)
    if (error) throw new Error('Il collegamento di accesso è scaduto. Riprova con Google.')
  })()
  callbacks.set(client, pending)
  // A retry can inspect the stored session again; a failed code requires a new login.
  void pending.catch(() => callbacks.delete(client))
  return pending
}
