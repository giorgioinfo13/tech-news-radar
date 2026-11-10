import { useEffect, useId, useRef, useState } from 'react'
import { useLanguage } from './language-context'
import { release, releaseStorageKey } from './release'

export function WhatsNew({ userId, onClose }: { userId: string; onClose: () => void }) {
  const { language } = useLanguage()
  const italian = language === 'it'
  const titleId = useId()
  const dialog = useRef<HTMLDialogElement>(null)
  const [hide, setHide] = useState(false)
  useEffect(() => {
    const element = dialog.current
    const previous = document.activeElement as HTMLElement | null
    element?.showModal()
    return () => {
      element?.close()
      previous?.focus()
    }
  }, [])
  function close() {
    if (hide) {
      try {
        localStorage.setItem(releaseStorageKey(userId), release.version)
      } catch {
        // Closing remains available when browser storage is blocked.
      }
    }
    onClose()
  }
  return (
    <dialog
      ref={dialog}
      className="whats-new"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        close()
      }}
    >
      <div className="whats-new-heading">
        <h2 id={titleId}>{italian ? 'Novità del sito' : 'What’s new'}</h2>
        <button
          type="button"
          autoFocus
          onClick={close}
          aria-label={italian ? 'Chiudi novità' : 'Close what’s new'}
        >
          ×
        </button>
      </div>
      <p>
        {italian ? 'Versione' : 'Version'} {release.version}
      </p>
      <label className="whats-new-preference">
        <input type="checkbox" checked={hide} onChange={(event) => setHide(event.target.checked)} />
        <span>
          {italian ? 'Non mostrare più per questa versione' : 'Don’t show again for this version'}
        </span>
      </label>
      <p className="whats-new-hint">
        {italian
          ? 'La scelta vale per questo account in questo browser.'
          : 'This choice applies to this account in this browser.'}
      </p>
      <ul>
        {release.changes[language].map((change) => (
          <li key={change}>{change}</li>
        ))}
      </ul>
    </dialog>
  )
}
