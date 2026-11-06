import { useState, type ReactNode } from 'react'
import logo from '../../docs/assets/tech-news-radar-logo.svg'
import { Notice } from './components'
import type { AuthController, AuthState } from './auth'
import { ThemeSelector } from './Theme'

function AccessLayout({ children }: { children: ReactNode }) {
  return (
    <main className="access-page">
      <div className="access-panel">
        <img className="access-logo" src={logo} alt="Tech News Radar" />
        {children}
        <ThemeSelector />
      </div>
    </main>
  )
}

export function Login({ controller, state }: { controller: AuthController; state: AuthState }) {
  const [pending, setPending] = useState(false)
  const login = async () => {
    setPending(true)
    await controller.login()
    setPending(false)
  }
  if (state.status === 'loading')
    return (
      <AccessLayout>
        <p role="status">Verifica dell’accesso…</p>
      </AccessLayout>
    )
  if (state.status === 'unconfigured')
    return (
      <AccessLayout>
        <h1>Il radar si sta preparando</h1>
        <p>L’accesso non è ancora disponibile. Contatta l’amministratore.</p>
      </AccessLayout>
    )
  if (state.status === 'denied')
    return (
      <AccessLayout>
        <h1>Accesso riservato</h1>
        <p>
          Questo account non è ancora autorizzato, oppure il suo accesso è stato revocato. Contatta
          l’amministratore per continuare.
        </p>
        <div className="actions">
          <button onClick={() => void controller.validate()}>Verifica di nuovo</button>
          <button onClick={() => void controller.logout()}>Esci</button>
        </div>
      </AccessLayout>
    )
  return (
    <AccessLayout>
      <h1>Un posto per le tue notizie.</h1>
      <p>
        Tecnologia, intelligenza artificiale ed economia. Scegli le fonti, ritrova le tue letture.
      </p>
      {state.message && <Notice error>{state.message}</Notice>}
      {state.status === 'error' && <button onClick={controller.retry}>Riprova</button>}
      {controller.configuration.mode === 'supabase' && (
        <>
          <button className="google-button" onClick={() => void login()} disabled={pending}>
            <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
              <path
                fill="#EA4335"
                d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
              />
              <path
                fill="#4285F4"
                d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
              />
              <path
                fill="#FBBC05"
                d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
              />
              <path
                fill="#34A853"
                d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
              />
            </svg>
            {pending ? 'Apertura di Google…' : 'Accedi con Google'}
          </button>
          <p className="muted">L’accesso è riservato alle persone autorizzate.</p>
        </>
      )}
    </AccessLayout>
  )
}
