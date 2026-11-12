import { message } from '../messages'
import type { UiMessage } from '../messages'
import { useLanguage } from '../language-context'
import { useEffect, useRef, useState } from 'react'
import { errorMessage, mutate, request, type Source, type Subscription } from '../api'
import { ConfirmDialog, Empty, Notice } from '../components'

export function Subscriptions({
  sources,
  subscriptions,
  onChange,
  initial = false,
  updating = false,
  onContinue,
}: {
  sources: Source[]
  subscriptions: Subscription[]
  onChange: () => void
  initial?: boolean
  updating?: boolean
  onContinue: () => void
}) {
  const { t } = useLanguage()
  const followed = new Set(subscriptions.map((item) => item.source_id))
  const [selected, setSelected] = useState(
    () => new Set(sources.filter((source) => source.enabled).map((source) => source.id)),
  )
  const [saving, setBusy] = useState(false)
  const busy = saving || updating
  const [confirmUnfollow, setConfirmUnfollow] = useState(false)
  const [error, setError] = useState<UiMessage | ''>('')
  const [notice, setMessage] = useState<UiMessage | ''>('')
  const lifetime = useRef(new AbortController())
  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    return () => controller.abort()
  }, [])
  async function changeAll(method: 'PUT' | 'DELETE') {
    const operation = lifetime.current
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await request<{ changed: number }>('/subscriptions', {
        method,
        signal: operation.signal,
      })
      setConfirmUnfollow(false)
      onChange()
      setMessage(
        method === 'PUT'
          ? message('Sources added to your follows: {count}.', { count: result.changed })
          : message('Sources unfollowed: {count}. Your reading history is kept.', {
              count: result.changed,
            }),
      )
    } catch (error) {
      if (!operation.signal.aborted) {
        setConfirmUnfollow(false)
        setError(errorMessage(error))
        // A lost response does not prove rollback. Reload before another action.
        onChange()
      }
    } finally {
      if (!operation.signal.aborted) setBusy(false)
    }
  }
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
        <a className="text-button" href="#proposals">
          {t('Suggest a source')}
        </a>
      </header>
      {error && !confirmUnfollow && (
        <Notice error>
          {t(error)} {initial && t('Previously saved choices are kept: you can try again.')}
        </Notice>
      )}
      {notice && <Notice>{t(notice)}</Notice>}
      <div className="subscription-toolbar" aria-busy={busy}>
        <p>
          {t(
            initial
              ? 'Selected sources: {count} of {total}'
              : 'You follow {count} of {total} sources',
            {
              count: initial ? selected.size : followed.size,
              total: sources.length,
            },
          )}
        </p>
        <div className="actions">
          <button
            className="primary-soft"
            disabled={
              busy || !sources.some((source) => !(initial ? selected : followed).has(source.id))
            }
            onClick={() =>
              initial
                ? setSelected(new Set(sources.map((source) => source.id)))
                : void changeAll('PUT')
            }
          >
            {t(initial ? 'Select all' : 'Follow all')}
          </button>
          <button
            disabled={busy || (initial ? selected.size === 0 : followed.size === 0)}
            onClick={() => {
              if (initial) setSelected(new Set())
              else {
                setError('')
                setConfirmUnfollow(true)
              }
            }}
          >
            {t(initial ? 'Deselect all' : 'Unfollow all')}
          </button>
        </div>
      </div>
      {saving && !confirmUnfollow && <p role="status">{t('Saving…')}</p>}
      {confirmUnfollow && (
        <ConfirmDialog
          title={t('Unfollow all sources?')}
          pending={saving}
          error={error}
          confirmLabel={t('Unfollow all')}
          pendingLabel={t('Saving…')}
          onCancel={() => {
            setConfirmUnfollow(false)
            setError('')
          }}
          onConfirm={() => void changeAll('DELETE')}
        >
          {t('Stop following all {count} sources? Your reading history will be kept.', {
            count: followed.size,
          })}
        </ConfirmDialog>
      )}
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
