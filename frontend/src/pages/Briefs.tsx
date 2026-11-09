import { useEffect, useState } from 'react'
import {
  briefStatusMessage,
  errorMessage,
  formatDate,
  request,
  safeArticleUrl,
  type BriefArticle,
  type BriefState,
} from '../api'
import { Notice, QueryState } from '../components'
import { Icon } from '../Icon'
import { useLanguage } from '../language-context'
import type { UiMessage } from '../messages'

export function Briefs() {
  const { t, locale } = useLanguage()
  const [state, setState] = useState<BriefState | null>(null)
  const [revision, setRevision] = useState(0)
  const [loadedRevision, setLoadedRevision] = useState(-1)
  const [error, setError] = useState<UiMessage | ''>('')
  const loading = loadedRevision !== revision
  useEffect(() => {
    const controller = new AbortController()
    request<BriefState>('/briefs/digest', { signal: controller.signal })
      .then((next) => {
        if (!controller.signal.aborted) {
          setState(next)
          setError('')
        }
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(errorMessage(cause))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadedRevision(revision)
      })
    return () => controller.abort()
  }, [revision])
  const code = state?.code
  const status =
    code === 'available' || code === 'cached' || code === 'scheduled_only'
      ? t('Hourly updates are scheduled. Delays or skipped editions are possible.')
      : code === 'unchanged'
        ? t('No new material for another edition. The latest digest remains available.')
        : code === 'edition_attempted'
          ? t('This hour’s attempt is complete. No retry is scheduled for this edition.')
          : code === 'category_cooldown'
            ? t('Generation is cooling down after a failed attempt.')
            : t(briefStatusMessage(code ?? 'disabled'))
  return (
    <>
      <header className="page-header">
        <div>
          <h1>{t('Last 24 hours digest')}</h1>
          <p>{t('One shared digest across the catalog, independent of the sources you follow.')}</p>
        </div>
      </header>
      <section className="editor-panel brief-controls" aria-label={t('AI digest')}>
        <p>{t('Last 24 hours · Up to 12 articles · Saved for 7 days')}</p>
        <p>
          {t(
            'Updated at most once an hour when new material is available. Reading or refreshing this page never generates a digest.',
          )}
        </p>
        <div className="brief-actions">
          <button disabled={loading} onClick={() => setRevision((v) => v + 1)}>
            <Icon name="refresh" />
            {t('Refresh list')}
          </button>
        </div>
        {state && (
          <div role="status" aria-live="polite">
            <p>{status}</p>
            {state.retry_at && (
              <p>
                {t('Next availability check')}:{' '}
                <time dateTime={state.retry_at}>{formatDate(state.retry_at, locale)}</time>
              </p>
            )}
            {state.last_error_code && state.last_error_code !== code && (
              <p>{t(briefStatusMessage(state.last_error_code))}</p>
            )}
          </div>
        )}
      </section>
      <QueryState loading={loading && !state} error="" retry={() => setRevision((v) => v + 1)} />
      {error && <Notice error>{t(error)}</Notice>}
      {state && (
        <section className="brief-results" aria-label={t('Saved editions')} aria-busy={loading}>
          {state.briefs.length === 0 && <p>{t('No saved digest yet.')}</p>}
          {state.briefs.map((brief, index) => (
            <article className="brief-card" key={brief.id}>
              <h2>{t(index === 0 ? 'Latest edition' : 'Previous edition')}</h2>
              <p className="muted">
                {t('Generated on')}:{' '}
                <time dateTime={brief.generated_at}>{formatDate(brief.generated_at, locale)}</time>
              </p>
              <p className="muted">
                {t('News interval')}: {formatDate(brief.window_start, locale)} –{' '}
                {formatDate(brief.window_end, locale)}
              </p>
              <p className="brief-summary" lang="it">
                {brief.summary}
              </p>
              <p className="form-hint">
                {t(
                  'Based on RSS titles and descriptions, not full articles. The Italian summary may contain errors: check the sources.',
                )}
              </p>
              <h3>{t('Articles used')}</h3>
              <ArticleLinks articles={brief.articles} />
            </article>
          ))}
          {state.briefs.length === 0 && state.articles.length > 0 && (
            <div className="brief-card">
              <h2>{t('Available articles')}</h2>
              <ArticleLinks articles={state.articles} />
            </div>
          )}
        </section>
      )}
    </>
  )
}

function ArticleLinks({ articles }: { articles: BriefArticle[] }) {
  const { t } = useLanguage()
  return (
    <ul className="brief-links">
      {articles.map((article) => {
        const url = safeArticleUrl(article.url)
        return (
          <li key={article.id}>
            {url ? (
              <a href={url} target="_blank" rel="noopener noreferrer">
                {article.title}
                <Icon name="external" />
              </a>
            ) : (
              article.title
            )}
            <span className="muted">
              {article.source}
              {article.category_name ? ` · ${article.category_name}` : ''}
            </span>
            {article.removed && (
              <small>{t('Removed from the reader; original source link preserved')}</small>
            )}
            {article.date_is_fetched && (
              <small>{t('Acquisition date used because publication date is missing')}</small>
            )}
          </li>
        )
      })}
    </ul>
  )
}
