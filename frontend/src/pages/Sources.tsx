import { usePanelFocus } from '../usePanelFocus'
import { useState, type FormEvent } from 'react'
import {
  errorMessage,
  formatDate,
  mutate,
  type Category,
  type CollectionRun,
  type Source,
} from '../api'
import { ConfirmDialog, Empty, Notice, Pagination, QueryState } from '../components'
import { useQuery } from '../useQuery'
import { Icon } from '../Icon'

type SourceInput = Pick<Source, 'name' | 'feed_url' | 'category_id' | 'enabled'>

function SourceEditor({
  source,
  categories,
  busy,
  onSave,
  onCancel,
}: {
  source?: Source
  categories: Category[]
  busy: boolean
  onSave: (input: SourceInput) => void
  onCancel: () => void
}) {
  const panelRef = usePanelFocus()
  const [name, setName] = useState(source?.name ?? '')
  const [url, setUrl] = useState(source?.feed_url ?? '')
  const [category, setCategory] = useState(source?.category_id?.toString() ?? '')
  const [enabled, setEnabled] = useState(source?.enabled ?? true)
  const [error, setError] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    try {
      const parsed = new URL(url.trim())
      if (
        !['http:', 'https:'].includes(parsed.protocol) ||
        parsed.username ||
        parsed.password ||
        parsed.hash
      )
        throw new Error()
    } catch {
      setError('Inserisci un URL HTTP o HTTPS senza credenziali o frammenti.')
      return
    }
    if (!name.trim()) {
      setError('Inserisci il nome della fonte.')
      return
    }
    setError('')
    onSave({
      name: name.trim(),
      feed_url: url.trim(),
      category_id: category ? Number(category) : null,
      enabled,
    })
  }
  return (
    <section
      ref={panelRef}
      tabIndex={-1}
      className="editor-panel"
      aria-labelledby="source-editor-title"
    >
      <h2 id="source-editor-title">{source ? `Modifica ${source.name}` : 'Aggiungi una fonte'}</h2>
      <p className="muted">
        Incolla l’indirizzo di un feed RSS o Atom. Potrai raccogliere gli articoli con Aggiorna.
      </p>
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="form-grid">
          <label>
            Nome della fonte
            <input
              name="source-name"
              autoComplete="off"
              required
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Il nome che vuoi vedere"
            />
          </label>
          <label>
            Categoria
            <select
              name="category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">Senza categoria</option>
              {categories.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="full-width">
            URL del feed
            <input
              type="url"
              name="feed-url"
              autoComplete="off"
              spellCheck={false}
              required
              maxLength={2048}
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://…"
            />
          </label>
          <label className="checkbox-label full-width">
            <input
              type="checkbox"
              name="enabled"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            Fonte attiva
          </label>
          {source && (
            <p className="form-hint full-width">
              Cambiare URL conserva gli articoli e la cronologia, ma azzera i dati dell’ultimo
              controllo.
            </p>
          )}
          {error && (
            <div className="full-width">
              <Notice error>{error}</Notice>
            </div>
          )}
          <div className="actions full-width">
            <button className="primary" type="submit">
              {busy ? 'Salvataggio…' : 'Salva fonte'}
            </button>
            <button type="button" onClick={onCancel}>
              Annulla
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  )
}

function History({ source, onClose }: { source: Source; onClose: () => void }) {
  const panelRef = usePanelFocus()
  const [offset, setOffset] = useState(0)
  const runs = useQuery<CollectionRun>(`/sources/${source.id}/runs?limit=10&offset=${offset}`)
  const labels = {
    running: 'In corso',
    success: 'Completato',
    not_modified: 'Nessuna modifica',
    error: 'Non riuscito',
  }
  return (
    <section
      ref={panelRef}
      tabIndex={-1}
      id={`source-history-${source.id}`}
      className="history-panel"
      aria-labelledby="history-title"
    >
      <div className="section-heading">
        <h2 id="history-title">Cronologia · {source.name}</h2>
        <button onClick={onClose}>Chiudi cronologia</button>
      </div>
      <QueryState loading={runs.loading} error={runs.error} retry={runs.reload} />
      {runs.data && (
        <>
          {runs.data.items.length ? (
            <ul className="history-list">
              {runs.data.items.map((run) => (
                <li key={run.id}>
                  <div>
                    <strong>{labels[run.status]}</strong>
                    <span>{formatDate(run.started_at)}</span>
                  </div>
                  <p>
                    {run.error_message ??
                      `${run.articles_added} nuovi articoli su ${run.articles_seen} elementi esaminati.`}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Nessun aggiornamento eseguito per questa fonte.</p>
          )}
          <Pagination offset={offset} total={runs.data.total} limit={10} onChange={setOffset} />
        </>
      )}
    </section>
  )
}

export function Sources({
  sources,
  categories,
  onChange,
}: {
  sources: Source[]
  categories: Category[]
  onChange: () => void
}) {
  const [editor, setEditor] = useState<Source | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Source | null>(null)
  const [history, setHistory] = useState<Source | null>(null)
  const [historyRevision, setHistoryRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  async function action(operation: () => Promise<unknown>, success: string, done?: () => void) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await operation()
      setMessage(success)
      done?.()
      onChange()
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  async function refresh(source: Source) {
    setBusy(true)
    setRefreshing(source.id)
    setError('')
    setMessage('')
    try {
      const run = await mutate<CollectionRun>(`/sources/${source.id}/refresh`, 'POST')
      setMessage(
        run.status === 'not_modified'
          ? `${source.name}: nessuna modifica al feed.`
          : `${source.name}: ${run.articles_added} nuovi articoli raccolti.`,
      )
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
      setRefreshing(null)
      onChange()
      setHistoryRevision((value) => value + 1)
    }
  }
  const editorPanel = editor && (
    <SourceEditor
      key={editor === 'new' ? 'new' : editor.id}
      source={editor === 'new' ? undefined : editor}
      categories={categories}
      busy={busy}
      onCancel={() => setEditor(null)}
      onSave={(input) =>
        void action(
          () =>
            mutate(
              editor === 'new' ? '/sources' : `/sources/${editor.id}`,
              editor === 'new' ? 'POST' : 'PATCH',
              input,
            ),
          'Fonte salvata.',
          () => setEditor(null),
        )
      }
    />
  )
  return (
    <>
      <header className="page-header">
        <div>
          <h1>Catalogo</h1>
          <p>Gestisci le fonti condivise da tutti i lettori.</p>
        </div>
        <button
          className="primary"
          disabled={busy}
          onClick={() => {
            setEditor('new')
            setError('')
            setMessage('')
          }}
        >
          Aggiungi fonte
        </button>
      </header>
      {message && <Notice>{message}</Notice>}
      {error && !deleting && <Notice error>{error}</Notice>}
      {refreshing !== null && (
        <Notice>Aggiornamento in corso… Può richiedere qualche secondo.</Notice>
      )}
      {editor === 'new' && editorPanel}
      <div className="section-heading">
        <h2>
          Fonti condivise <span>{sources.length}</span>
        </h2>
        <span className="muted">Aggiornamenti manuali</span>
      </div>
      {!sources.length ? (
        <Empty title="Da dove vuoi iniziare?">
          Aggiungi il feed di un sito che segui. Nessuna fonte viene aggiunta automaticamente.
        </Empty>
      ) : (
        <div className="source-list">
          {sources.map((source) => (
            <article className="source-card" key={source.id}>
              <div className="source-card-header">
                <div>
                  <div className="source-title">
                    <h3>{source.name}</h3>
                    <span className={`badge ${source.enabled ? 'enabled' : ''}`}>
                      {source.enabled ? 'Attiva' : 'In pausa'}
                    </span>
                  </div>
                  <p className="source-overview">{source.category?.name ?? 'Senza categoria'}</p>
                </div>
                <div className="source-actions">
                  <button
                    className="primary-soft"
                    disabled={busy || !source.enabled}
                    aria-label={`Aggiorna ${source.name}`}
                    onClick={() => void refresh(source)}
                  >
                    <Icon name="refresh" />{' '}
                    {refreshing === source.id ? 'Aggiornamento…' : 'Aggiorna'}
                  </button>
                  <button
                    disabled={busy}
                    aria-label={`Modifica ${source.name}`}
                    onClick={() => {
                      setEditor(source)
                      setError('')
                      setMessage('')
                    }}
                  >
                    Modifica
                  </button>
                </div>
              </div>
              {source.last_error && (
                <p className="source-error">
                  Ultimo aggiornamento non riuscito: {source.last_error}
                </p>
              )}
              <details className="source-details">
                <summary aria-label={`Dettagli e azioni ${source.name}`}>Dettagli e azioni</summary>
                <div className="source-detail-content">
                  <p className="feed-url">{source.feed_url}</p>
                  <div className="source-dates">
                    <span>
                      Ultimo controllo <strong>{formatDate(source.last_checked_at)}</strong>
                    </span>
                    <span>
                      Ultimo esito positivo <strong>{formatDate(source.last_success_at)}</strong>
                    </span>
                  </div>
                  <div className="source-actions">
                    <button
                      disabled={busy}
                      aria-label={`${source.enabled ? 'Disattiva' : 'Attiva'} ${source.name}`}
                      onClick={() =>
                        void action(
                          () =>
                            mutate(`/sources/${source.id}`, 'PATCH', { enabled: !source.enabled }),
                          source.enabled ? 'Fonte messa in pausa.' : 'Fonte attivata.',
                        )
                      }
                    >
                      {source.enabled ? 'Metti in pausa' : 'Attiva'}
                    </button>
                    <button
                      id={`history-trigger-${source.id}`}
                      aria-label={`Cronologia ${source.name}`}
                      aria-expanded={history?.id === source.id}
                      aria-controls={
                        history?.id === source.id ? `source-history-${source.id}` : undefined
                      }
                      onClick={() => setHistory(source)}
                    >
                      Cronologia
                    </button>
                    <button
                      className="text-danger"
                      disabled={busy}
                      aria-label={`Elimina ${source.name}`}
                      onClick={() => {
                        setDeleting(source)
                        setError('')
                      }}
                    >
                      Elimina
                    </button>
                  </div>
                </div>
              </details>
              {editor !== 'new' && editor?.id === source.id && editorPanel}
              {history?.id === source.id && (
                <History
                  key={`${history.id}:${historyRevision}`}
                  source={history}
                  onClose={() => {
                    setHistory(null)
                    document.getElementById(`history-trigger-${source.id}`)?.focus()
                  }}
                />
              )}
            </article>
          ))}
        </div>
      )}
      {deleting && (
        <ConfirmDialog
          title={`Eliminare ${deleting.name}?`}
          pending={busy}
          error={error}
          onCancel={() => {
            setDeleting(null)
            setError('')
          }}
          onConfirm={() =>
            void action(
              () => mutate(`/sources/${deleting.id}`, 'DELETE'),
              'Fonte eliminata.',
              () => {
                setDeleting(null)
                setEditor(null)
                if (history?.id === deleting.id) setHistory(null)
              },
            )
          }
        >
          Verranno eliminati definitivamente anche tutti gli articoli e la cronologia di questa
          fonte. Questa operazione non può essere annullata.
        </ConfirmDialog>
      )}
    </>
  )
}
