import type { UiMessage } from '../messages'
import { message } from '../messages'
import { useLanguage } from '../language-context'
import { useState, type FormEvent } from 'react'
import { ApiError, errorMessage, formatDate, mutate, type ReaderInvitation } from '../api'
import { Empty, Notice, Pagination, QueryState } from '../components'
import { useQuery } from '../useQuery'

export function Invitations() {
  const { t, locale } = useLanguage()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [notice, setMessage] = useState<UiMessage | ''>('')
  const [error, setError] = useState<UiMessage | ''>('')
  const invitations = useQuery<ReaderInvitation>(`/invitations?limit=20&offset=${offset}`)

  async function add(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await mutate('/invitations', 'POST', { email: email.trim(), display_name: name.trim() })
      setEmail('')
      setName('')
      setOffset(0)
      invitations.reload()
      setMessage(message('Invitation saved. Share the website link with this person.'))
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 409
          ? message(
              'An invitation already exists for this email. Check the list before trying again.',
            )
          : errorMessage(cause),
      )
    } finally {
      setBusy(false)
    }
  }

  async function cancel(invitation: ReaderInvitation) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await mutate(`/invitations/${invitation.id}`, 'DELETE')
      setMessage(message('Invitation for {email} canceled.', { email: invitation.email }))
      if (invitations.data?.items.length === 1 && offset > 0) setOffset(offset - 20)
      else invitations.reload()
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 409
          ? message('The invitation is no longer pending. Refresh the list to check its status.')
          : errorMessage(cause),
      )
      invitations.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h1>{t('Invitations')}</h1>
          <p>{t('Choose who can join your reading space.')}</p>
        </div>
      </header>
      <section className="editor-panel" aria-labelledby="invitation-title">
        <h2 id="invitation-title">{t('Invite a reader')}</h2>
        <p className="form-hint" id="invitation-hint">
          {t(
            'Enter the Google account email, even before the first sign-in. The person can join as a reader. No email is sent automatically.',
          )}
        </p>
        <form onSubmit={(event) => void add(event)} aria-describedby="invitation-hint">
          <fieldset className="form-grid" disabled={busy}>
            <label>
              {t('Name')}
              <input
                name="display-name"
                autoComplete="off"
                required
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label>
              {t('Google email')}
              <input
                name="email"
                type="email"
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                required
                maxLength={254}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <div className="actions full-width">
              <button className="primary" type="submit">
                {busy ? t('Saving…') : t('Save invitation')}
              </button>
            </div>
          </fieldset>
        </form>
      </section>
      {error && <Notice error>{t(error)}</Notice>}
      {notice && <Notice>{t(notice)}</Notice>}
      <section aria-labelledby="invitation-list-title">
        <div className="page-header">
          <h2 id="invitation-list-title">{t('Saved invitations')}</h2>
          <button disabled={busy || invitations.loading} onClick={invitations.reload}>
            {t('Refresh list')}
          </button>
        </div>
        <QueryState
          loading={invitations.loading}
          error={invitations.error}
          retry={invitations.reload}
        />
        {invitations.data?.items.length === 0 && (
          <Empty title={t('Choose the next reader')}>
            {t(
              'Add an email address to allow someone to sign in for the first time. Previously approved users are not listed here.',
            )}
          </Empty>
        )}
        {invitations.data?.items.map((invitation) => (
          <article className="category-card" key={invitation.id}>
            <div className="invitation-details">
              <h3>{invitation.display_name}</h3>
              <p>{invitation.email}</p>
              <p className="muted">
                {invitation.accepted_at ? t('Used') : t('Pending')} ·{' '}
                {formatDate(invitation.accepted_at ?? invitation.created_at, locale)}
              </p>
            </div>
            {!invitation.accepted_at && (
              <button
                disabled={busy}
                onClick={() => void cancel(invitation)}
                aria-label={t('Cancel invitation for {email}', { email: invitation.email })}
              >
                {t('Cancel invitation')}
              </button>
            )}
          </article>
        ))}
        {invitations.data && (
          <Pagination
            offset={offset}
            limit={20}
            total={invitations.data.total}
            onChange={setOffset}
          />
        )}
        <p className="form-hint">
          {t(
            'Used invitations cannot be canceled. To revoke an active reader’s access, use the administration procedure in Terminal.',
          )}
        </p>
      </section>
    </>
  )
}
