export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}
export interface Category {
  id: number
  name: string
  slug: string
  sort_order: number
}
export interface Source {
  id: number
  name: string
  feed_url: string
  category_id: number | null
  category: Category | null
  enabled: boolean
  refresh_interval_minutes: number
  last_checked_at: string | null
  last_success_at: string | null
  last_error: string | null
  consecutive_failures: number
  created_at: string
}
export interface Article {
  id: number
  source_id: number
  source: Pick<Source, 'id' | 'name' | 'category'>
  title: string
  description: string | null
  url: string
  published_at: string | null
  fetched_at: string
  is_read: boolean
}
export interface CollectionRun {
  id: number
  source_id: number
  started_at: string
  finished_at: string | null
  status: 'running' | 'success' | 'not_modified' | 'error'
  articles_seen: number
  articles_added: number
  error_message: string | null
}

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Impossibile contattare il server. Verifica che il backend sia avviato.', 0)
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      404: 'Questo elemento non esiste più. Aggiorna la pagina.',
      409: 'Operazione non disponibile: verifica eventuali duplicati, fonti disabilitate o un refresh in corso.',
      422: 'Controlla i dati inseriti: uno o più valori non sono validi.',
      502: 'Il refresh non è riuscito. Consulta lo stato della fonte e la cronologia per i dettagli.',
    }
    const delay = response.headers.get('Retry-After')
    const retry =
      delay && /^\d{1,6}$/.test(delay) ? ` Riprova tra ${delay} secondi.` : ' Riprova più tardi.'
    throw new ApiError(
      response.status === 429
        ? `Aggiornamento troppo ravvicinato.${retry}`
        : (messages[response.status] ?? 'Il server non ha completato la richiesta. Riprova.'),
      response.status,
    )
  }
  if (response.status === 204) return undefined as T
  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError('Il server ha restituito una risposta non valida.', response.status)
  }
}

export function mutate<T>(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown) {
  return request<T>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
}

export async function allPages<T>(path: string, signal: AbortSignal): Promise<Page<T>> {
  const items: T[] = []
  let total: number
  do {
    const page = await request<Page<T>>(`${path}?limit=100&offset=${items.length}`, { signal })
    items.push(...page.items)
    total = page.total
    if (!page.items.length) break
  } while (items.length < total)
  return { items, total: items.length, limit: items.length, offset: 0 }
}

export function safeArticleUrl(value: string): string | null {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password
      ? url.href
      : null
  } catch {
    return null
  }
}

export function formatDate(value: string | null): string {
  if (!value) return 'Mai'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? 'Data non disponibile'
    : new Intl.DateTimeFormat('it-IT', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Operazione non riuscita. Riprova.'
}
