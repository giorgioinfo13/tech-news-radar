import { useEffect, useState, useSyncExternalStore } from 'react'
import { type Category, type Source, type Subscription, type AppUser } from './api'
import { AuthController } from './auth'
import { authConfiguration } from './auth-client'
import { Login } from './Login'
import { Subscriptions } from './pages/Subscriptions'
import radar from '../../docs/assets/tech-news-radar-icon-circular.svg'
import { QueryState } from './components'
import { Dashboard } from './pages/Dashboard'
import { Sources } from './pages/Sources'
import { Categories } from './pages/Categories'
import { useQuery } from './useQuery'
import { Icon } from './Icon'
import { ThemeProvider, ThemeSelector } from './Theme'

function currentPage() {
  return ['sources', 'catalog', 'categories'].includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : 'news'
}

export default function App({ controller: supplied }: { controller?: AuthController } = {}) {
  return (
    <ThemeProvider>
      <AuthenticatedApp supplied={supplied} />
    </ThemeProvider>
  )
}

function AuthenticatedApp({ supplied }: { supplied?: AuthController }) {
  const [controller] = useState(() => supplied ?? new AuthController(authConfiguration()))
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot)
  useEffect(() => controller.start(), [controller])
  return state.status === 'ready' && state.user ? (
    <ReaderApp
      key={`${state.user.id}:${state.user.role}`}
      user={state.user}
      controller={controller}
    />
  ) : (
    <Login controller={controller} state={state} />
  )
}

function ReaderApp({ user, controller }: { user: AppUser; controller: AuthController }) {
  const [page, setPage] = useState(currentPage)
  const subscriptions = useQuery<Subscription>('/subscriptions', true)
  const admin = user.role === 'admin'
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
    subscriptions.reload()
  }
  const ready = categories.data && sources.data && subscriptions.data
  const pages = [
    { id: 'news', label: 'Notizie', icon: 'news' },
    { id: 'sources', label: 'Le mie fonti', icon: 'sources' },
    { id: 'catalog', label: 'Catalogo', icon: 'sources' },
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
            <img src={radar} alt="" />
          </span>
          <span>
            Tech News<span className="brand-sub">Radar</span>
          </span>
        </a>
        <nav aria-label="Navigazione principale">
          {pages
            .filter((item) => admin || !['catalog', 'categories'].includes(item.id))
            .map((item) => (
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
        <div className="account-menu">
          <p>{user.display_name}</p>
          <span className="muted">{admin ? 'Amministratore' : 'Lettore'}</span>
          {controller.configuration.mode !== 'local' && (
            <button onClick={() => void controller.logout()}>Esci</button>
          )}
        </div>
        <ThemeSelector />
        <div className="sidebar-note">
          <p>Il tuo spazio di lettura.</p>
          <a href="#sources">Scegli le fonti da seguire</a>
          <p>
            <a href="/privacy.html">Privacy e dati personali</a>
          </p>
        </div>
      </aside>
      <main id="main-content" tabIndex={-1}>
        <QueryState
          loading={(categories.loading || sources.loading || subscriptions.loading) && !ready}
          error={categories.error || sources.error || subscriptions.error}
          retry={reloadCatalog}
        />
        {categories.data && sources.data && subscriptions.data && (
          <Workspace
            page={page}
            admin={admin}
            sources={sources.data.items}
            categories={categories.data.items}
            subscriptions={subscriptions.data.items}
            reloadCatalog={reloadCatalog}
            reloadSubscriptions={subscriptions.reload}
          />
        )}
      </main>
    </div>
  )
}

function Workspace({
  page,
  admin,
  sources,
  categories,
  subscriptions,
  reloadCatalog,
  reloadSubscriptions,
}: {
  page: string
  admin: boolean
  sources: Source[]
  categories: Category[]
  subscriptions: Subscription[]
  reloadCatalog: () => void
  reloadSubscriptions: () => void
}) {
  const [onboarding, setOnboarding] = useState(() => subscriptions.length === 0)
  const finish = () => {
    setOnboarding(false)
    location.hash = '#news'
  }
  if (onboarding)
    return (
      <Subscriptions
        initial
        sources={sources}
        subscriptions={subscriptions}
        onChange={reloadSubscriptions}
        onContinue={finish}
      />
    )
  const personalSources = sources.filter((source) =>
    subscriptions.some((item) => item.source_id === source.id),
  )
  if (page === 'sources')
    return (
      <Subscriptions
        sources={sources}
        subscriptions={subscriptions}
        onChange={reloadSubscriptions}
        onContinue={finish}
      />
    )
  if (admin && page === 'catalog')
    return <Sources sources={sources} categories={categories} onChange={reloadCatalog} />
  if (admin && page === 'categories')
    return <Categories categories={categories} onChange={reloadCatalog} />
  return <Dashboard categories={categories} sources={personalSources} />
}
