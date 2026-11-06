import { useEffect, useRef, useState } from 'react'
import { errorMessage, mutate, request, type Source, type Subscription } from '../api'
import { Empty, Notice } from '../components'

export function Subscriptions({
  sources,
  subscriptions,
  onChange,
  initial = false,
  onContinue,
}: {
  sources: Source[]
  subscriptions: Subscription[]
  onChange: () => void
  initial?: boolean
  onContinue: () => void
}) {
  const followed = new Set(subscriptions.map((item) => item.source_id))
  const [selected, setSelected] = useState(
    () => new Set(sources.filter((source) => source.enabled).map((source) => source.id)),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const lifetime = useRef(new AbortController())
  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    return () => controller.abort()
  }, [])
  async function save() {
    const operation = lifetime.current
    setBusy(true)
    setError('')
    try {
      for (const id of selected) {
        await request(`/subscriptions/${id}`, { method: 'PUT', signal: operation.signal })
      }
      onChange()
      onContinue()
    } catch (error) {
      if (!operation.signal.aborted) setError(errorMessage(error))
    } finally {
      if (!operation.signal.aborted) setBusy(false)
    }
  }
  async function toggle(source: Source) {
    const operation = lifetime.current
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await request(`/subscriptions/${source.id}`, {
        method: followed.has(source.id) ? 'DELETE' : 'PUT',
        signal: operation.signal,
      })
      onChange()
      setMessage(
        followed.has(source.id)
          ? `Non segui più ${source.name}. Le letture sono conservate.`
          : `Ora segui ${source.name}.`,
      )
    } catch (error) {
      if (!operation.signal.aborted) setError(errorMessage(error))
    } finally {
      if (!operation.signal.aborted) setBusy(false)
    }
  }
  async function refresh(source: Source) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await mutate(`/sources/${source.id}/refresh`, 'POST')
      setMessage(`${source.name}: aggiornamento completato.`)
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <header className="page-header">
        <div>
          <h1>{initial ? 'Scegli da dove iniziare' : 'Le mie fonti'}</h1>
          <p>
            {initial
              ? 'Ti proponiamo le fonti del catalogo. Scegli quelle che vuoi nel tuo radar.'
              : 'Segui ciò che ti interessa. Le tue scelte non cambiano quelle degli altri.'}
          </p>
        </div>
      </header>
      {error && (
        <Notice error>
          {error} {initial && 'Le scelte già salvate restano valide: puoi riprovare.'}
        </Notice>
      )}
      {message && <Notice>{message}</Notice>}
      {!sources.length ? (
        <Empty title="Il catalogo è in preparazione">
          L’amministratore aggiungerà le fonti da cui scegliere.
        </Empty>
      ) : (
        <div className="subscription-list">
          {sources.map((source) => (
            <article className="subscription-row" key={source.id}>
              {initial ? (
                <label className="subscription-choice">
                  <input
                    type="checkbox"
                    checked={selected.has(source.id)}
                    disabled={busy}
                    onChange={() =>
                      setSelected((previous) => {
                        const next = new Set(previous)
                        if (next.has(source.id)) next.delete(source.id)
                        else next.add(source.id)
                        return next
                      })
                    }
                  />
                  <span>
                    <strong>{source.name}</strong>
                    <span className="muted">
                      {source.category?.name ?? 'Senza categoria'}
                      {!source.enabled && ' · Raccolta in pausa'}
                    </span>
                  </span>
                </label>
              ) : (
                <>
                  <div>
                    <h2>{source.name}</h2>
                    <p className="muted">
                      {source.category?.name ?? 'Senza categoria'}
                      {!source.enabled && ' · Raccolta in pausa'}
                    </p>
                  </div>
                  <div className="actions">
                    {followed.has(source.id) && (
                      <button
                        disabled={busy || !source.enabled}
                        onClick={() => void refresh(source)}
                        aria-label={`Aggiorna ${source.name}`}
                      >
                        Aggiorna
                      </button>
                    )}
                    <button
                      className={followed.has(source.id) ? '' : 'primary-soft'}
                      disabled={busy}
                      aria-pressed={followed.has(source.id)}
                      aria-label={`${followed.has(source.id) ? 'Non seguire più' : 'Segui'} ${source.name}`}
                      onClick={() => void toggle(source)}
                    >
                      {followed.has(source.id) ? 'Seguita' : 'Segui'}
                    </button>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      )}
      {initial && (
        <div className="onboarding-actions">
          <p>Puoi cambiare queste scelte in qualsiasi momento.</p>
          <div className="actions">
            <button
              className="primary"
              disabled={busy || !selected.size}
              onClick={() => void save()}
            >
              {busy
                ? 'Salvataggio…'
                : `Segui ${selected.size} ${selected.size === 1 ? 'fonte' : 'fonti'} e continua`}
            </button>
            <button disabled={busy} onClick={onContinue}>
              Non ora
            </button>
          </div>
        </div>
      )}
    </>
  )
}
