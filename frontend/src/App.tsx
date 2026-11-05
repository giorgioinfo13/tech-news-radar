import { useEffect, useState } from 'react'
import { type Category, type Source } from './api'
import { QueryState } from './components'
import { Dashboard } from './pages/Dashboard'
import { Sources } from './pages/Sources'
import { Categories } from './pages/Categories'
import { useQuery } from './useQuery'

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
    { id: 'news', label: 'Notizie', icon: '◫' },
    { id: 'sources', label: 'Fonti', icon: '◉' },
    { id: 'categories', label: 'Categorie', icon: '▦' },
  ]
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Vai al contenuto
      </a>
      <aside className="sidebar">
        <a href="#news" className="brand">
          <span className="radar-logo" aria-hidden="true">
            ◎
          </span>
          <span>
            Tech News<span className="brand-sub">RADAR</span>
          </span>
        </a>
        <p className="nav-caption">IL TUO SPAZIO</p>
        <nav aria-label="Navigazione principale">
          {pages.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              aria-current={page === item.id ? 'page' : undefined}
            >
              <span aria-hidden="true">{item.icon}</span>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="status-dot" />
          Un radar, le tue fonti.<p>Le notizie che scegli, in un unico posto.</p>
        </div>
      </aside>
      <main id="main-content" tabIndex={-1}>
        <div className="topbar">
          <span>TECNOLOGIA · IDEE · RICERCA</span>
          <span className="local-badge">Spazio personale</span>
        </div>
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
