import { useState, type ReactNode } from 'react'
import logo from '../../docs/assets/tech-news-radar-logo.svg'
import { Notice } from './components'
import type { AuthController, AuthState } from './auth'
import { AccountMenu } from './AccountMenu'
import { GoogleSignInButton } from './GoogleSignInButton'

function AccessLayout({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="access-page">
      <header className="access-toolbar">
        <AccountMenu>{actions}</AccountMenu>
      </header>
      <main className="access-content">
        <div className="access-panel">
          <img className="access-logo" src={logo} alt="Tech News Radar" />
          {children}
        </div>
      </main>
      <footer className="access-footer">
        <a href="/privacy.html">Privacy e dati personali</a>
      </footer>
    </div>
  )
}

export function Login({ controller, state }: { controller: AuthController; state: AuthState }) {
  const [pending, setPending] = useState(false)
  const login = async () => {
    setPending(true)
    await controller.login()
    setPending(false)
  }
  const signIn = <GoogleSignInButton onClick={() => void login()} pending={pending} />
  if (state.status === 'loading')
    return (
      <AccessLayout>
        <p role="status">Verifica dell’accesso…</p>
        <p className="muted">
          Al primo accesso il server può richiedere circa un minuto per avviarsi.
        </p>
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
      <AccessLayout actions={<button onClick={() => void controller.logout()}>Esci</button>}>
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
    <AccessLayout actions={controller.configuration.mode === 'supabase' ? signIn : undefined}>
      <h1>Un posto per le tue notizie.</h1>
      <p>
        Tecnologia, intelligenza artificiale ed economia.
        <br />
        Scegli le fonti, ritrova le tue letture.
      </p>
      {state.message && <Notice error>{state.message}</Notice>}
      {state.status === 'error' && <button onClick={controller.retry}>Riprova</button>}
      {controller.configuration.mode === 'supabase' && (
        <>
          {signIn}
          <p className="muted">L’accesso è riservato alle persone autorizzate.</p>
        </>
      )}
    </AccessLayout>
  )
}
