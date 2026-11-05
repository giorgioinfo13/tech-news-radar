import { useState, type FormEvent } from 'react'
import {
  errorMessage,
  formatDate,
  mutate,
  safeArticleUrl,
  type Article,
  type Category,
  type Source,
} from '../api'
import { Empty, Notice, Pagination, QueryState } from '../components'
import { useQuery } from '../useQuery'

export function Dashboard({ categories, sources }: { categories: Category[]; sources: Source[] }) {
  const [filters, setFilters] = useState({ category: '', source: '', read: '', q: '', offset: 0 })
  const [search, setSearch] = useState('')
  const [pending, setPending] = useState<number | null>(null)
  const [error, setError] = useState('')
  const params = new URLSearchParams({ limit: '20', offset: String(filters.offset) })
  if (filters.category) params.set('category_id', filters.category)
  if (filters.source) params.set('source_id', filters.source)
  if (filters.read) params.set('is_read', filters.read)
  if (filters.q) params.set('q', filters.q)
  const articles = useQuery<Article>(`/articles?${params}`)
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
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">IL TUO RADAR</p>
          <h1>Uno sguardo sulle notizie.</h1>
          <p>Segui ciò che conta, dalle fonti che hai scelto.</p>
        </div>
        <a href="#sources" className="button primary">
          Gestisci fonti <span aria-hidden="true">↗</span>
        </a>
      </header>
      <section className="filter-panel" aria-label="Filtri notizie">
        <form className="search" onSubmit={submitSearch}>
          <label className="sr-only" htmlFor="search">
            Cerca nelle notizie
          </label>
          <span aria-hidden="true">⌕</span>
          <input
            id="search"
            type="search"
            placeholder="Cerca un argomento, un’idea…"
            maxLength={200}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <button type="submit">Cerca</button>
        </form>
        <div className="filter-row">
          <label>
            Fonte
            <select
              value={filters.source}
              onChange={(event) => filter('source', event.target.value)}
            >
              <option value="">Tutte le fonti</option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Categoria
            <select
              value={filters.category}
              onChange={(event) => filter('category', event.target.value)}
            >
              <option value="">Tutte le categorie</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="read-filter">
            <legend>Stato di lettura</legend>
            {[
              { value: '', label: 'Tutte' },
              { value: 'false', label: 'Da leggere' },
              { value: 'true', label: 'Lette' },
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
          Le ultime notizie <span>{articles.data?.total ?? '—'}</span>
        </h2>
        {activeFilters ? (
          <button
            className="text-button"
            onClick={() => {
              setSearch('')
              setFilters({ category: '', source: '', read: '', q: '', offset: 0 })
            }}
          >
            Azzera filtri
          </button>
        ) : (
          <span className="muted">Più recenti per prime</span>
        )}
      </div>
      {error && <Notice error>{error}</Notice>}
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
                    <span className="category-tag">
                      {article.source.category?.name ?? 'Senza categoria'}
                    </span>
                    <span className="read-label">{article.is_read ? 'Letto' : 'Da leggere'}</span>
                  </div>
                  <h3>
                    {href ? (
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {article.title}
                        <span aria-hidden="true" className="external-arrow">
                          ↗
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
                    <span>
                      {article.published_at ? (
                        <time dateTime={article.published_at}>
                          {formatDate(article.published_at)}
                        </time>
                      ) : (
                        <>Data non disponibile · raccolto {formatDate(article.fetched_at)}</>
                      )}
                    </span>
                    <button
                      className="text-button"
                      disabled={pending !== null}
                      aria-label={`${article.is_read ? 'Segna da leggere' : 'Segna come letto'}: ${article.title}`}
                      onClick={() => void toggleRead(article)}
                    >
                      {pending === article.id
                        ? 'Salvataggio…'
                        : article.is_read
                          ? 'Segna da leggere'
                          : 'Segna come letto'}
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <Empty
            title={
              sources.length ? 'Nessuna notizia da mostrare' : 'Il tuo radar parte da una fonte'
            }
          >
            {sources.length
              ? 'Prova altri filtri oppure aggiorna una fonte per raccogliere nuovi articoli.'
              : 'Aggiungi il tuo primo feed RSS o Atom e avvia un aggiornamento dalla pagina Fonti.'}{' '}
            <a href="#sources">Vai alle fonti</a>
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
    </>
  )
}
