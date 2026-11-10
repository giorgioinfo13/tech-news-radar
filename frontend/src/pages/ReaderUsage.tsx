import { formatDate } from '../api'
import { useState } from 'react'
import { Empty, QueryState } from '../components'
import { useLanguage } from '../language-context'
import { useQuery } from '../useQuery'

export interface ReaderUsage {
  id: string
  display_name: string
  created_at: string
  last_seen_at: string | null
  followed_sources: number
  read_articles: number
  last_read_at: string | null
}

export function ReaderUsagePanel() {
  const { t, locale } = useLanguage()
  const usage = useQuery<ReaderUsage>('/usage/readers', true)
  // This is a snapshot refreshed explicitly, not a live presence indicator.
  const [now, setNow] = useState(() => Date.now())
  const refresh = () => {
    setNow(Date.now())
    usage.reload()
  }
  const readers = usage.data?.items ?? []
  const recent = (days: number) =>
    readers.filter(
      (reader) => reader.last_seen_at && Date.parse(reader.last_seen_at) >= now - days * 86400000,
    ).length
  return (
    <section aria-labelledby="reader-usage-title">
      <div className="page-header">
        <h2 id="reader-usage-title">{t('Reader usage')}</h2>
        <button disabled={usage.loading} onClick={refresh}>
          {t('Refresh usage')}
        </button>
      </div>
      <p className="form-hint">
        {t(
          'App access checks are approximate and can include automatic session renewals. No history before activation is available. This does not show who is online.',
        )}
      </p>
      <QueryState loading={usage.loading} error={usage.error} retry={refresh} />
      {usage.data && (
        <>
          <p>
            {t(
              'Authorized: {total} · Seen in 7 days: {week} · Seen in 30 days: {month} · Not yet recorded: {unknown}',
              {
                total: readers.length,
                week: recent(7),
                month: recent(30),
                unknown: readers.filter((reader) => !reader.last_seen_at).length,
              },
            )}
          </p>
          {readers.length === 0 && <Empty title={t('No authorized readers yet.')}>{null}</Empty>}
          {readers.map((reader) => (
            <article className="category-card" key={reader.id}>
              <div className="invitation-details">
                <h3>{reader.display_name}</h3>
                <p>
                  {t('Last recorded access')}:{' '}
                  {reader.last_seen_at
                    ? formatDate(reader.last_seen_at, locale)
                    : t('Not yet recorded')}
                </p>
                <p>
                  {t('Profile created')}: {formatDate(reader.created_at, locale)}
                </p>
                <p>
                  {t('Followed sources: {sources} · Articles currently marked read: {articles}', {
                    sources: reader.followed_sources,
                    articles: reader.read_articles,
                  })}
                </p>
                <p>
                  {t('Latest saved read mark')}:{' '}
                  {reader.last_read_at
                    ? formatDate(reader.last_read_at, locale)
                    : t('Not yet recorded')}
                </p>
              </div>
            </article>
          ))}
        </>
      )}
    </section>
  )
}
