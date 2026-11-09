import { message } from '../messages'
import type { UiMessage } from '../messages'
import { useLanguage } from '../language-context'
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
  const { t } = useLanguage()
  const followed = new Set(subscriptions.map((item) => item.source_id))
  const [selected, setSelected] = useState(
    () => new Set(sources.filter((source) => source.enabled).map((source) => source.id)),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<UiMessage | ''>('')
  const [notice, setMessage] = useState<UiMessage | ''>('')
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
          ? message('You no longer follow {name}. Your reading history is kept.', {
              name: source.name,
            })
          : message('You now follow {name}.', { name: source.name }),
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
      setMessage(message('{name}: refresh completed.', { name: source.name }))
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
          <h1>{initial ? t('Choose where to start') : t('My sources')}</h1>
          <p>
            {initial
              ? t('Here are the sources in the catalog. Choose the ones you want on your radar.')
              : t('Follow what interests you.')}
          </p>
        </div>
      </header>
      {error && (
        <Notice error>
          {t(error)} {initial && t('Previously saved choices are kept: you can try again.')}
        </Notice>
      )}
      {notice && <Notice>{t(notice)}</Notice>}
      {!sources.length ? (
        <Empty title={t('The catalog is being prepared')}>
          {t('The administrator will add sources for you to choose from.')}
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
                      {source.category?.name ?? t('Uncategorized')}
                      {!source.enabled && t(' · Collection paused')}
                    </span>
                  </span>
                </label>
              ) : (
                <>
                  <div>
                    <h2>{source.name}</h2>
                    <p className="muted">
                      {source.category?.name ?? t('Uncategorized')}
                      {!source.enabled && t(' · Collection paused')}
                    </p>
                  </div>
                  <div className="actions">
                    {followed.has(source.id) && (
                      <button
                        disabled={busy || !source.enabled}
                        onClick={() => void refresh(source)}
                        aria-label={t('Refresh {name}', { name: source.name })}
                      >
                        {t('Refresh')}
                      </button>
                    )}
                    <button
                      className={followed.has(source.id) ? '' : 'primary-soft'}
                      disabled={busy}
                      aria-pressed={followed.has(source.id)}
                      aria-label={`${followed.has(source.id) ? t('Unfollow') : t('Follow')} ${source.name}`}
                      onClick={() => void toggle(source)}
                    >
                      {followed.has(source.id) ? t('Unfollow') : t('Follow')}
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
          <p>{t('You can change these choices at any time.')}</p>
          <div className="actions">
            <button
              className="primary"
              disabled={busy || !selected.size}
              onClick={() => void save()}
            >
              {busy
                ? t('Saving…')
                : t(
                    selected.size === 1
                      ? 'Follow {count} source and continue'
                      : 'Follow {count} sources and continue',
                    { count: selected.size },
                  )}
            </button>
            <button disabled={busy} onClick={onContinue}>
              {t('Not now')}
            </button>
          </div>
        </div>
      )}
    </>
  )
}
