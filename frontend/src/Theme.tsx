import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from 'react'

type Preference = 'system' | 'light' | 'dark'
const storageKey = 'tnr-theme'
const ThemeContext = createContext<{
  preference: Preference
  change: (value: Preference) => void
} | null>(null)

function preferenceFrom(value: string | null): Preference {
  return value === 'light' || value === 'dark' ? value : 'system'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<Preference>(() => {
    try {
      return preferenceFrom(localStorage.getItem(storageKey))
    } catch {
      return 'system'
    }
  })

  useLayoutEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const apply = () => {
      const dark = preference === 'dark' || (preference === 'system' && media?.matches)
      document.documentElement.dataset.theme = dark ? 'dark' : 'light'
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute('content', dark ? '#141e2b' : '#f4f6f8')
    }
    apply()
    media?.addEventListener('change', apply)
    return () => media?.removeEventListener('change', apply)
  }, [preference])

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key !== storageKey && event.key !== null) return
      try {
        if (event.storageArea !== localStorage) return
      } catch {
        return
      }
      setPreference(preferenceFrom(event.newValue))
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  const change = (value: Preference) => {
    setPreference(value)
    try {
      localStorage.setItem(storageKey, value)
    } catch {
      // Keep the choice for this page even when persistent storage is unavailable.
    }
  }
  return <ThemeContext value={{ preference, change }}>{children}</ThemeContext>
}

export function ThemeSelector() {
  const theme = useContext(ThemeContext)
  if (!theme) return null
  return (
    <label className="theme-selector">
      Tema
      <select
        value={theme.preference}
        onChange={(event) => theme.change(preferenceFrom(event.target.value))}
      >
        <option value="system">Sistema</option>
        <option value="light">Chiaro</option>
        <option value="dark">Scuro</option>
      </select>
    </label>
  )
}
