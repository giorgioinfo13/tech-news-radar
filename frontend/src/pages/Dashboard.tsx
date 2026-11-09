import type { UiMessage } from '../messages'
import { useLanguage } from '../language-context'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  errorMessage,
  ApiError,
  formatDate,
  mutate,
  safeArticleUrl,
  type Article,
  type Category,
  type Source,
  type RefreshSummary,
} from '../api'
import { Empty, Notice, Pagination, QueryState } from '../components'
import { useQuery } from '../useQuery'
import { Icon } from '../Icon'
import { usePullToRefresh } from '../usePullToRefresh'
import { message } from '../messages'

export function Dashboard({ categories, sources }: { categories: Category[]; sources: Source[] }) {
  const { t, locale } = useLanguage()
  const [filters, setFilters] = useState({ category: '', source: '', read: '', q: '', offset: 0 })
  const [search, setSearch] = useState('')
  const [pending, setPending] = useState<number | null>(null)
  const [error, setError] = useState<UiMessage | ''>('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const filterCount = [filters.source, filters.category, filters.read].filter(Boolean).length
  const params = new URLSearchParams({ limit: '20', offset: String(filters.offset) })
  if (filters.category) params.set('category_id', filters.category)
  if (filters.source) params.set('source_id', filters.source)
  if (filters.read) params.set('is_read', filters.read)
  if (filters.q) params.set('q', filters.q)
  const articles = useQuery<Article>(`/articles?${params}`)
  const [refreshing, setRefreshing] = useState(false)
  const [cooling, setCooling] = useState(false)
  const [refreshResult, setRefreshResult] = useState<RefreshSummary | null>(null)
  const [refreshError, setRefreshError] = useState<UiMessage | null>(null)
  const refreshLock = useRef(false)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const reload = articles.reload
  const refresh = useCallback(async () => {
    if (refreshLock.current) return
    refreshLock.current = true
    setRefreshing(true)
    setRefreshError(null)
    setRefreshResult(null)
    try {
      const result = await mutate<RefreshSummary>('/sources/refresh', 'POST')
      if (mounted.current) setRefreshResult(result)
    } catch (error) {
      if (mounted.current)
        setRefreshError(
          error instanceof ApiError && error.status === 409
            ? message('A collection is already in progress. No new collection was started.')
            : errorMessage(error),
        )
    } finally {
      // A short UI debounce also covers gestures immediately after the response.
      if (mounted.current) {
        setRefreshing(false)
        setCooling(true)
        reload()
      }
    }
  }, [reload])
  useEffect(() => {
    if (!cooling) return
    const timer = window.setTimeout(() => {
      refreshLock.current = false
      setCooling(false)
    }, 3000)
    return () => window.clearTimeout(timer)
  }, [cooling])
  const { surface: pullSurface, pulling, ready } = usePullToRefresh(refresh, refreshing || cooling)
  function filter(key: 'category' | 'source' | 'read' | 'q', value: string) {
    setFilters((previous) => ({ ...previous, [key]: value, offset: 0 }))
  }
  function submitSearch(event: FormEvent) {
    event.preventDefault()
    filter('q', search.trim())
  }
  async function toggleRead(article: Article) {
    setPending(article.id)
    setError('')
    try {
      await mutate(`/articles/${article.id}`, 'PATCH', { is_read: !article.is_read })
      if (articles.data?.items.length === 1 && filters.offset > 0 && filters.read) {
        setFilters((previous) =>
          previous === filters
            ? { ...previous, offset: Math.max(0, previous.offset - 20) }
            : previous,
        )
      }
      articles.reload()
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setPending(null)
    }
  }
  const activeFilters = filters.category || filters.source || filters.read || filters.q
  return (
    <div ref={pullSurface} className="news-refresh-surface">
      <header className="page-header">
        <div>
          <h1>{t('News')}</h1>
          <p>{t('Your sources, one read at a time.')}</p>
        </div>
        <div className="actions header-action">
          <button onClick={() => void refresh()} disabled={refreshing || cooling}>
            <Icon name="refresh" />
            {refreshing ? t('Refreshing sources…') : t('Refresh sources')}
          </button>
          <a href="#sources" className="button">
            {t('Choose sources')}
          </a>
        </div>
      </header>
      {pulling && (
        <p className="pull-feedback" role="status">
          {ready ? t('Release to refresh sources') : t('Pull down to refresh sources')}
        </p>
      )}
      {refreshing && <Notice>{t('Checking RSS sources. This may take a moment.')}</Notice>}
      {refreshError && <Notice error>{t(refreshError)}</Notice>}
      {refreshResult && (
        <Notice error={refreshResult.failed > 0}>
          {t(
            'New articles: {added} · Sources checked: {checked} · Skipped: {skipped} · Failed: {failed}.',
            {
              added: refreshResult.added,
              checked: refreshResult.checked,
              skipped: refreshResult.skipped,
              failed: refreshResult.failed,
            },
          )}
          {refreshResult.deferred > 0 && (
            <>
              {' '}
              {t('Partial update: {count} sources remain. No automatic retry.', {
                count: refreshResult.deferred,
              })}
            </>
          )}
          {refreshResult.checked === 0 && refreshResult.deferred === 0 && (
            <>
              {' '}
              {refreshResult.retry_after
                ? t(
                    'Sources were checked recently or are waiting after errors. Next check in at least {seconds} seconds.',
                    { seconds: refreshResult.retry_after },
                  )
                : t('No enabled sources are available to refresh.')}
            </>
          )}
        </Notice>
      )}
      <section className="filter-panel" aria-label={t('News filters')}>
        <form className="search" onSubmit={submitSearch}>
          <label className="sr-only" htmlFor="search">
            {t('Search news')}
          </label>
          <Icon name="search" />
          <input
            id="search"
            type="search"
            name="q"
            autoComplete="off"
            placeholder={t('Search news…')}
            maxLength={200}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <button type="submit">{t('Search')}</button>
        </form>
        <button
          className="filter-toggle"
          aria-expanded={filtersOpen}
          aria-controls="news-filters"
          onClick={() => setFiltersOpen(!filtersOpen)}
        >
          <Icon name="filter" /> {t('Filters')}
          {filterCount > 0
            ? ` (${t(filterCount === 1 ? '{count} active filter' : '{count} active filters', { count: filterCount })})`
            : ''}
          <span aria-hidden="true">{filtersOpen ? '−' : '+'}</span>
        </button>
        <div id="news-filters" className={`filter-row ${filtersOpen ? 'is-open' : ''}`}>
          <label>
            {t('Source')}
            <select
              name="source"
              value={filters.source}
              onChange={(event) => filter('source', event.target.value)}
            >
              <option value="">{t('All sources')}</option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Category')}
            <select
              name="category"
              value={filters.category}
              onChange={(event) => filter('category', event.target.value)}
            >
              <option value="">{t('All categories')}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="read-filter">
            <legend>{t('Reading status')}</legend>
            {[
              { value: '', label: t('All') },
              { value: 'false', label: t('Unread') },
              { value: 'true', label: t('Read') },
            ].map((item) => (
              <button
                type="button"
                key={item.value}
                aria-pressed={filters.read === item.value}
                onClick={() => filter('read', item.value)}
              >
                {item.label}
              </button>
            ))}
          </fieldset>
        </div>
      </section>
      <div className="section-heading">
        <h2>
          {t('Latest news')}{' '}
          <span>
            {articles.data ? new Intl.NumberFormat(locale).format(articles.data.total) : '—'}
          </span>
        </h2>
        {activeFilters ? (
          <button
            className="text-button"
            onClick={() => {
              setSearch('')
              setFilters({ category: '', source: '', read: '', q: '', offset: 0 })
            }}
          >
            {t('Clear filters')}
          </button>
        ) : (
          <span className="muted">{t('Newest first')}</span>
        )}
      </div>
      {error && <Notice error>{t(error)}</Notice>}
      <QueryState loading={articles.loading} error={articles.error} retry={articles.reload} />
      {articles.data &&
        (articles.data.items.length ? (
          <div className="article-list">
            {articles.data.items.map((article) => {
              const href = safeArticleUrl(article.url)
              return (
                <article
                  className={`article-card ${article.is_read ? 'is-read' : ''}`}
                  key={article.id}
                >
                  <div className="article-meta">
                    <span className="source-name">
                      <span className="source-initial" aria-hidden="true">
                        {article.source.name.slice(0, 1).toUpperCase()}
                      </span>
                      {article.source.name}
                    </span>
                    <span className="article-date">
                      {article.published_at ? (
                        <time dateTime={article.published_at}>
                          {formatDate(article.published_at, locale)}
                        </time>
                      ) : (
                        <>
                          {t('Date unavailable · collected')}{' '}
                          {formatDate(article.fetched_at, locale)}
                        </>
                      )}
                    </span>
                  </div>
                  <h3>
                    {href ? (
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {article.title}
                        <span className="external-arrow">
                          <Icon name="external" />
                        </span>
                      </a>
                    ) : (
                      article.title
                    )}
                  </h3>
                  {article.description && (
                    <p className="article-description">{article.description}</p>
                  )}
                  <div className="article-footer">
                    <span className="category-tag">
                      {article.source.category?.name ?? t('Uncategorized')}
                    </span>
                    <button
                      className="text-button"
                      disabled={pending !== null}
                      aria-label={`${article.is_read ? t('Mark as unread') : t('Mark as read')}: ${article.title}`}
                      onClick={() => void toggleRead(article)}
                    >
                      {article.is_read && <Icon name="check" />}
                      {pending === article.id
                        ? t('Saving…')
                        : article.is_read
                          ? t('Mark as unread')
                          : t('Mark as read')}
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <Empty
            title={sources.length ? t('No news to show') : t('Your radar starts with a source')}
          >
            {sources.length
              ? t('Try other filters or refresh a source to collect new articles.')
              : t('Choose sources to follow and start reading.')}{' '}
            <a href="#sources">{t('Go to sources')}</a>
          </Empty>
        ))}
      {articles.data && (
        <Pagination
          offset={filters.offset}
          total={articles.data.total}
          limit={20}
          onChange={(offset) => setFilters((previous) => ({ ...previous, offset }))}
        />
      )}
    </div>
  )
}
