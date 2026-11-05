import { useEffect, useState } from 'react'
import { type Category, type Source } from './api'
import { QueryState } from './components'
import { Dashboard } from './pages/Dashboard'
import { Sources } from './pages/Sources'
import { Categories } from './pages/Categories'
import { useQuery } from './useQuery'
import { Icon } from './Icon'

function currentPage() {
  return ['sources', 'categories'].includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : 'news'
}

export default function App() {
  const [page, setPage] = useState(currentPage)
  const categories = useQuery<Category>('/categories', true)
  const sources = useQuery<Source>('/sources', true)
  useEffect(() => {
    const navigate = () => {
      if (location.hash !== '#main-content') setPage(currentPage())
    }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  const reloadCatalog = () => {
    categories.reload()
    sources.reload()
  }
  const ready = categories.data && sources.data
  const pages = [
    { id: 'news', label: 'Notizie', icon: 'news' },
    { id: 'sources', label: 'Fonti', icon: 'sources' },
    { id: 'categories', label: 'Categorie', icon: 'categories' },
  ] as const
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Vai al contenuto
      </a>
      <aside className="sidebar">
        <a href="#news" className="brand" translate="no">
          <span className="radar-logo" aria-hidden="true">
            <Icon name="radar" />
          </span>
          <span>
            Tech News<span className="brand-sub">Radar</span>
          </span>
        </a>
        <nav aria-label="Navigazione principale">
          {pages.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              aria-current={page === item.id ? 'page' : undefined}
            >
              <Icon name={item.icon} />
              {item.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <p>Il tuo spazio di lettura.</p>
          <a href="#sources">Scegli le fonti da seguire</a>
        </div>
      </aside>
      <main id="main-content" tabIndex={-1}>
        <QueryState
          loading={(categories.loading || sources.loading) && !ready}
          error={categories.error || sources.error}
          retry={reloadCatalog}
        />
        {categories.data && sources.data && (
          <>
            {page === 'news' && (
              <Dashboard categories={categories.data.items} sources={sources.data.items} />
            )}
            {page === 'sources' && (
              <Sources
                sources={sources.data.items}
                categories={categories.data.items}
                onChange={sources.reload}
              />
            )}
            {page === 'categories' && (
              <Categories categories={categories.data.items} onChange={reloadCatalog} />
            )}
          </>
        )}
      </main>
    </div>
  )
}
