import { useLanguage } from './language-context'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import type { AppUser } from './api'
import { Icon } from './Icon'
import { ThemeSelector } from './Theme'
import { LanguageSelector } from './Language'
import { WhatsNew } from './WhatsNew'
import { release, shouldShowRelease } from './release'

export function AccountMenu({ user, children }: { user?: AppUser; children?: ReactNode }) {
  const { t, privacyHref, language } = useLanguage()
  const [showNews, setShowNews] = useState(() => !!user && shouldShowRelease(user.id))
  const [open, setOpen] = useState(false)
  const id = useId()
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        trigger.current?.focus()
      }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  return (
    <div
      className="account-menu"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
      }}
    >
      <button
        type="button"
        className="account-menu-toggle"
        ref={trigger}
        aria-label={t('Account and appearance menu')}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <Icon name="menu" />
        <span>{t('Menu')}</span>
      </button>
      {open && (
        <div
          id={id}
          className="account-popover"
          role="region"
          aria-label={t('Account and appearance')}
        >
          {user && (
            <div className="account-identity">
              <p>{user.display_name}</p>
              <span className="muted">
                {user.role === 'admin' ? t('Administrator') : t('Reader')}
              </span>
            </div>
          )}
          <ThemeSelector />
          <LanguageSelector />
          {children && <div className="account-actions">{children}</div>}
          <a href={privacyHref}>{t('Privacy and personal data')}</a>
          {user && (
            <button
              className="release-menu-button"
              onClick={() => {
                setOpen(false)
                trigger.current?.focus()
                setShowNews(true)
              }}
            >
              {language === 'it' ? 'Versione' : 'Version'} {release.version} ·{' '}
              {language === 'it' ? 'Novità' : 'What’s new'}
            </button>
          )}
        </div>
      )}
      {user && showNews && <WhatsNew userId={user.id} onClose={() => setShowNews(false)} />}
    </div>
  )
}
