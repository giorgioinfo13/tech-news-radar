import type { UiMessage } from '../messages'
import { message } from '../messages'
import { useLanguage } from '../language-context'
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
  const { t } = useLanguage()
  const panelRef = usePanelFocus()
  const [name, setName] = useState(source?.name ?? '')
  const [url, setUrl] = useState(source?.feed_url ?? '')
  const [category, setCategory] = useState(source?.category_id?.toString() ?? '')
  const [enabled, setEnabled] = useState(source?.enabled ?? true)
  const [error, setError] = useState<UiMessage | ''>('')
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
      setError(message('Enter an HTTP or HTTPS URL without credentials or fragments.'))
      return
    }
    if (!name.trim()) {
      setError(message('Enter a source name.'))
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
      <h2 id="source-editor-title">
        {source ? t('Edit {name}', { name: source.name }) : t('Add a source')}
      </h2>
      <p className="muted">
        {t('Paste an RSS or Atom feed URL. Use Refresh to collect articles.')}
      </p>
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="form-grid">
          <label>
            {t('Source name')}
            <input
              name="source-name"
              autoComplete="off"
              required
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('The name you want to see')}
            />
          </label>
          <label>
            {t('Category')}
            <select
              name="category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">{t('Uncategorized')}</option>
              {categories.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="full-width">
            {t('Feed URL')}
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
            {t('Source enabled')}
          </label>
          {source && (
            <p className="form-hint full-width">
              {t('Changing the URL keeps articles and history, but resets the last check details.')}
            </p>
          )}
          {error && (
            <div className="full-width">
              <Notice error>{t(error)}</Notice>
            </div>
          )}
          <div className="actions full-width">
            <button className="primary" type="submit">
              {busy ? t('Saving…') : t('Save source')}
            </button>
            <button type="button" onClick={onCancel}>
              {t('Cancel')}
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  )
}

function History({ source, onClose }: { source: Source; onClose: () => void }) {
  const { t, locale } = useLanguage()
  const panelRef = usePanelFocus()
  const [offset, setOffset] = useState(0)
  const runs = useQuery<CollectionRun>(`/sources/${source.id}/runs?limit=10&offset=${offset}`)
  const labels = {
    running: t('Running'),
    success: t('Completed'),
    not_modified: t('No changes'),
    error: t('Failed'),
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
        <h2 id="history-title">
          {t('History ·')} {source.name}
        </h2>
        <button onClick={onClose}>{t('Close history')}</button>
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
                    <span>{formatDate(run.started_at, locale)}</span>
                  </div>
                  <p>
                    {run.error_message ??
                      t('{added} new articles out of {seen} items checked.', {
                        added: run.articles_added,
                        seen: run.articles_seen,
                      })}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t('This source has not been refreshed yet.')}</p>
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
  const { t, locale } = useLanguage()
  const [editor, setEditor] = useState<Source | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Source | null>(null)
  const [history, setHistory] = useState<Source | null>(null)
  const [historyRevision, setHistoryRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState<number | null>(null)
  const [error, setError] = useState<UiMessage | ''>('')
  const [notice, setMessage] = useState<UiMessage | ''>('')
  async function action(operation: () => Promise<unknown>, success: UiMessage, done?: () => void) {
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
          ? message('{name}: no changes to the feed.', { name: source.name })
          : message('{name}: {count} new articles collected.', {
              name: source.name,
              count: run.articles_added,
            }),
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
          message('Source saved.'),
          () => setEditor(null),
        )
      }
    />
  )
  return (
    <>
      <header className="page-header">
        <div>
          <h1>{t('Catalog')}</h1>
          <p>{t('Manage the sources shared by all readers.')}</p>
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
          {t('Add source')}
        </button>
      </header>
      {notice && <Notice>{t(notice)}</Notice>}
      {error && !deleting && <Notice error>{t(error)}</Notice>}
      {refreshing !== null && <Notice>{t('Refreshing… This may take a few seconds.')}</Notice>}
      {editor === 'new' && editorPanel}
      <div className="section-heading">
        <h2>
          {t('Shared sources')} <span>{sources.length}</span>
        </h2>
        <span className="muted">{t('Manual updates')}</span>
      </div>
      {!sources.length ? (
        <Empty title={t('Where would you like to start?')}>
          {t('Add the feed of a website you follow. No sources are added automatically.')}
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
                      {source.enabled ? t('Active') : t('Paused')}
                    </span>
                  </div>
                  <p className="source-overview">{source.category?.name ?? t('Uncategorized')}</p>
                </div>
                <div className="source-actions">
                  <button
                    className="primary-soft"
                    disabled={busy || !source.enabled}
                    aria-label={t('Refresh {name}', { name: source.name })}
                    onClick={() => void refresh(source)}
                  >
                    <Icon name="refresh" />{' '}
                    {refreshing === source.id ? t('Refreshing…') : t('Refresh')}
                  </button>
                  <button
                    disabled={busy}
                    aria-label={t('Edit {name}', { name: source.name })}
                    onClick={() => {
                      setEditor(source)
                      setError('')
                      setMessage('')
                    }}
                  >
                    {t('Edit')}
                  </button>
                </div>
              </div>
              {source.last_error && (
                <p className="source-error">
                  {t('Last refresh failed:')} {source.last_error}
                </p>
              )}
              <details className="source-details">
                <summary aria-label={t('Details and actions for {name}', { name: source.name })}>
                  {t('Details and actions')}
                </summary>
                <div className="source-detail-content">
                  <p className="feed-url">{source.feed_url}</p>
                  <div className="source-dates">
                    <span>
                      {t('Last checked')}{' '}
                      <strong>{formatDate(source.last_checked_at, locale)}</strong>
                    </span>
                    <span>
                      {t('Last successful refresh')}{' '}
                      <strong>{formatDate(source.last_success_at, locale)}</strong>
                    </span>
                  </div>
                  <div className="source-actions">
                    <button
                      disabled={busy}
                      aria-label={`${source.enabled ? t('Disable') : t('Enable')} ${source.name}`}
                      onClick={() =>
                        void action(
                          () =>
                            mutate(`/sources/${source.id}`, 'PATCH', { enabled: !source.enabled }),
                          source.enabled ? message('Source paused.') : message('Source enabled.'),
                        )
                      }
                    >
                      {source.enabled ? t('Pause') : t('Enable')}
                    </button>
                    <button
                      id={`history-trigger-${source.id}`}
                      aria-label={t('History for {name}', { name: source.name })}
                      aria-expanded={history?.id === source.id}
                      aria-controls={
                        history?.id === source.id ? `source-history-${source.id}` : undefined
                      }
                      onClick={() => setHistory(source)}
                    >
                      {t('History')}
                    </button>
                    <button
                      className="text-danger"
                      disabled={busy}
                      aria-label={t('Delete {name}', { name: source.name })}
                      onClick={() => {
                        setDeleting(source)
                        setError('')
                      }}
                    >
                      {t('Delete')}
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
          title={t('Delete {name}?', { name: deleting.name })}
          pending={busy}
          error={error}
          onCancel={() => {
            setDeleting(null)
            setError('')
          }}
          onConfirm={() =>
            void action(
              () => mutate(`/sources/${deleting.id}`, 'DELETE'),
              message('Source deleted.'),
              () => {
                setDeleting(null)
                setEditor(null)
                if (history?.id === deleting.id) setHistory(null)
              },
            )
          }
        >
          {t(
            'All articles and history for this source will also be permanently deleted. This action cannot be undone.',
          )}
        </ConfirmDialog>
      )}
    </>
  )
}
