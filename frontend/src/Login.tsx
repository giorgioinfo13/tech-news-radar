import { useLanguage } from './language-context'
import { useState, type ReactNode } from 'react'
import logo from '../../docs/assets/tech-news-radar-logo.svg'
import { Notice } from './components'
import type { AuthController, AuthState } from './auth'
import { AccountMenu } from './AccountMenu'
import { GoogleSignInButton } from './GoogleSignInButton'

function AccessLayout({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  const { t, privacyHref } = useLanguage()
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
        <a href={privacyHref}>{t('Privacy and personal data')}</a>
      </footer>
    </div>
  )
}

export function Login({ controller, state }: { controller: AuthController; state: AuthState }) {
  const { t } = useLanguage()
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
        <p role="status">{t('Checking access…')}</p>
        <p className="muted">
          {t('On your first visit, the server may take about a minute to start.')}
        </p>
      </AccessLayout>
    )
  if (state.status === 'unconfigured')
    return (
      <AccessLayout>
        <h1>{t('Your radar is getting ready')}</h1>
        <p>{t('Sign-in is not available yet. Contact the administrator.')}</p>
      </AccessLayout>
    )
  if (state.status === 'denied')
    return (
      <AccessLayout
        actions={<button onClick={() => void controller.logout()}>{t('Sign out')}</button>}
      >
        <h1>{t('Restricted access')}</h1>
        <p>
          {t(
            'This account has not been approved, or its access has been revoked. Contact the administrator to continue.',
          )}
        </p>
        <div className="actions">
          <button onClick={() => void controller.validate()}>{t('Check again')}</button>
          <button onClick={() => void controller.logout()}>{t('Sign out')}</button>
        </div>
      </AccessLayout>
    )
  return (
    <AccessLayout actions={controller.configuration.mode === 'supabase' ? signIn : undefined}>
      <h1>{t('A place for your news.')}</h1>
      <p>
        {t('Technology, artificial intelligence and economics.')}
        <br />
        {t('Choose your sources. Pick up where you left off.')}
      </p>
      {state.message && <Notice error>{t(state.message)}</Notice>}
      {state.status === 'error' && <button onClick={controller.retry}>{t('Try again')}</button>}
      {controller.configuration.mode === 'supabase' && (
        <>
          {signIn}
          <p className="muted">{t('Access is restricted to approved users.')}</p>
        </>
      )}
    </AccessLayout>
  )
}
