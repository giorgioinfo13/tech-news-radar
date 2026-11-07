import { useState, type FormEvent } from 'react'
import { ApiError, errorMessage, formatDate, mutate, type ReaderInvitation } from '../api'
import { Empty, Notice, Pagination, QueryState } from '../components'
import { useQuery } from '../useQuery'

export function Invitations() {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
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
      setMessage('Invito salvato. Condividi il link del sito con questa persona.')
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 409
          ? 'Esiste già un invito per questa email. Controlla l’elenco prima di riprovare.'
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
      setMessage(`Invito per ${invitation.email} annullato.`)
      if (invitations.data?.items.length === 1 && offset > 0) setOffset(offset - 20)
      else invitations.reload()
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 409
          ? 'L’invito non è più in attesa. Aggiorna l’elenco per verificarne lo stato.'
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
          <h1>Inviti</h1>
          <p>Decidi chi può entrare nel tuo spazio di lettura.</p>
        </div>
      </header>
      <section className="editor-panel" aria-labelledby="invitation-title">
        <h2 id="invitation-title">Invita un lettore</h2>
        <p className="form-hint" id="invitation-hint">
          Inserisci l’email dell’account Google, anche prima del primo accesso. La persona potrà
          entrare come lettore. Non viene inviata un’email automatica.
        </p>
        <form onSubmit={(event) => void add(event)} aria-describedby="invitation-hint">
          <fieldset className="form-grid" disabled={busy}>
            <label>
              Nome
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
              Email Google
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
                {busy ? 'Salvataggio…' : 'Salva invito'}
              </button>
            </div>
          </fieldset>
        </form>
      </section>
      {error && <Notice error>{error}</Notice>}
      {message && <Notice>{message}</Notice>}
      <section aria-labelledby="invitation-list-title">
        <div className="page-header">
          <h2 id="invitation-list-title">Inviti salvati</h2>
          <button disabled={busy || invitations.loading} onClick={invitations.reload}>
            Aggiorna elenco
          </button>
        </div>
        <QueryState
          loading={invitations.loading}
          error={invitations.error}
          retry={invitations.reload}
        />
        {invitations.data?.items.length === 0 && (
          <Empty title="Il prossimo lettore lo scegli tu">
            Aggiungi un’email per consentire il primo accesso. Gli utenti già approvati non sono
            elencati qui.
          </Empty>
        )}
        {invitations.data?.items.map((invitation) => (
          <article className="category-card" key={invitation.id}>
            <div className="invitation-details">
              <h3>{invitation.display_name}</h3>
              <p>{invitation.email}</p>
              <p className="muted">
                {invitation.accepted_at ? 'Utilizzato' : 'In attesa'} ·{' '}
                {formatDate(invitation.accepted_at ?? invitation.created_at)}
              </p>
            </div>
            {!invitation.accepted_at && (
              <button
                disabled={busy}
                onClick={() => void cancel(invitation)}
                aria-label={`Annulla invito per ${invitation.email}`}
              >
                Annulla invito
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
          Gli inviti utilizzati non si possono annullare. Per revocare un lettore già attivo resta
          disponibile la procedura di amministrazione da Terminale.
        </p>
      </section>
    </>
  )
}
