import { useEffect, useRef, type ReactNode } from 'react'
import { Icon } from './Icon'

export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return (
    <div className={`notice ${error ? 'notice-error' : ''}`} role={error ? 'alert' : 'status'}>
      {children}
    </div>
  )
}

export function QueryState({
  loading,
  error,
  retry,
}: {
  loading: boolean
  error?: string
  retry: () => void
}) {
  if (loading)
    return (
      <p className="loading" role="status">
        Caricamento…
      </p>
    )
  if (error)
    return (
      <Notice error>
        {error}{' '}
        <button className="text-button" onClick={retry}>
          Riprova
        </button>
      </Notice>
    )
  return null
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-mark" aria-hidden="true">
        <Icon name="radar" />
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  )
}

export function Pagination({
  offset,
  total,
  limit,
  onChange,
}: {
  offset: number
  total: number
  limit: number
  onChange: (offset: number) => void
}) {
  return (
    <nav className="pagination" aria-label="Paginazione">
      <span>
        {total ? `${offset + 1}–${Math.min(offset + limit, total)} di ${total}` : '0 risultati'}
      </span>
      <div className="actions">
        <button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Precedenti
        </button>
        <button disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          Successivi
        </button>
      </div>
    </nav>
  )
}

export function ConfirmDialog({
  title,
  children,
  pending,
  error,
  onCancel,
  onConfirm,
}: {
  title: string
  children: ReactNode
  pending: boolean
  error?: string
  onCancel: () => void
  onConfirm: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    const previous = document.activeElement as HTMLElement | null
    dialog?.showModal()
    return () => {
      dialog?.close()
      previous?.focus()
    }
  }, [])
  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-title"
      onCancel={(event) => {
        event.preventDefault()
        if (!pending) onCancel()
      }}
    >
      <h2 id="confirm-title">{title}</h2>
      <p>{children}</p>
      {error && <Notice error>{error}</Notice>}
      <div className="actions dialog-actions">
        <button autoFocus onClick={onCancel} disabled={pending}>
          Annulla
        </button>
        <button className="danger" disabled={pending} onClick={onConfirm}>
          {pending ? 'Eliminazione…' : 'Elimina definitivamente'}
        </button>
      </div>
    </dialog>
  )
}
