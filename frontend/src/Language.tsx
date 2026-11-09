import { useEffect, useLayoutEffect, useState, type ReactNode } from 'react'
import { LanguageContext, languageFrom, languageStorageKey, useLanguage } from './language-context'
import type { Language } from './messages'

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() => {
    try {
      return languageFrom(localStorage.getItem(languageStorageKey))
    } catch {
      return 'it'
    }
  })
  useLayoutEffect(() => {
    document.documentElement.lang = language
  }, [language])
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key !== languageStorageKey && event.key !== null) return
      try {
        if (event.storageArea !== localStorage) return
      } catch {
        return
      }
      setLanguage(languageFrom(event.newValue))
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])
  const changeLanguage = (next: Language) => {
    setLanguage(next)
    try {
      localStorage.setItem(languageStorageKey, next)
    } catch {
      // Keep the preference for this page when persistent storage is unavailable.
    }
  }
  return <LanguageContext value={{ language, changeLanguage }}>{children}</LanguageContext>
}

export function LanguageSelector() {
  const { language, changeLanguage, t } = useLanguage()
  return (
    <label className="language-selector">
      {t('Language')}
      <select
        value={language}
        onChange={(event) => changeLanguage(languageFrom(event.target.value))}
      >
        <option value="it" lang="it">
          Italiano
        </option>
        <option value="en" lang="en">
          English
        </option>
      </select>
    </label>
  )
}
