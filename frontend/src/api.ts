import { message, translate, type UiMessage } from './messages'
export interface ReaderInvitation {
  id: string
  email: string
  display_name: string
  created_at: string
  accepted_at: string | null
}
export interface AppUser {
  id: string
  display_name: string
  role: 'admin' | 'reader'
}
export interface Subscription {
  source_id: number
  source: Source
  created_at: string
}

type Credentials = {
  identity: string
  token: () => Promise<string | null>
  failure: (status: number) => void
}
let credentials: Credentials | undefined
let identityController = new AbortController()
export function configureIdentity(next?: Credentials) {
  if (next?.identity !== credentials?.identity || !next) {
    identityController.abort()
    identityController = new AbortController()
  }
  credentials = next
}

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

export interface RefreshSummary {
  checked: number
  added: number
  failed: number
  skipped: number
  deferred: number
  retry_after: number | null
}

export class ApiError extends Error {
  readonly status: number
  constructor(
    readonly uiMessage: UiMessage,
    status: number,
  ) {
    super(translate(uiMessage, 'it'))
    this.status = status
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const access = credentials
  if (!access) throw new ApiError(message('Sign in to continue.'), 401)
  const identitySignal = identityController.signal
  const signal = AbortSignal.any([
    identitySignal,
    ...(options.signal ? [options.signal] : []),
    // Render Free can take about a minute to wake. Stay below the proxy's 120s limit.
    AbortSignal.timeout(90000),
  ])
  let response: Response
  try {
    signal.throwIfAborted()
    const token = await access.token()
    signal.throwIfAborted()
    if (access.identity !== 'local' && !token) {
      access.failure(401)
      throw new ApiError(message('Your session has expired. Sign in again.'), 401)
    }
    const headers = new Headers(options.headers)
    if (options.body) headers.set('Content-Type', 'application/json')
    headers.delete('Authorization')
    if (token) headers.set('Authorization', `Bearer ${token}`)
    response = await fetch(`/api${path}`, {
      ...options,
      headers,
      signal,
      credentials: 'omit',
      cache: 'no-store',
      referrerPolicy: 'no-referrer',
    })
    signal.throwIfAborted()
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (identitySignal.aborted || options.signal?.aborted)
      throw new DOMException('Aborted', 'AbortError')
    throw new ApiError(
      options.method && !['GET', 'HEAD'].includes(options.method.toUpperCase())
        ? message(
            'The result could not be confirmed. Reload the page to check before repeating the action.',
          )
        : message(
            'Unable to reach the server: it may be starting up. Wait a minute and try again.',
          ),
      0,
    )
  }
  if (response.status === 401 || (response.status === 403 && path !== '/me'))
    access.failure(response.status)
  if (!response.ok) {
    if (path.startsWith('/briefs/')) {
      const body = await response.json().catch(() => null)
      if (['daily_limit', 'monthly_budget'].includes(body?.detail?.code))
        throw new ApiError(briefStatusMessage(body.detail.code), response.status)
    }
    const messages: Record<number, UiMessage> = {
      401: message('Your session has expired. Sign in again.'),
      403: message('This account is not authorized.'),
      503: message('The service is temporarily unavailable. Try again shortly.'),
      504: message('The server is taking too long. Wait a minute and reload the page.'),
      404: message('This item no longer exists. Reload the page.'),
      409: message(
        'Action unavailable: check for duplicates, disabled sources or a refresh in progress.',
      ),
      422: message('Check the details you entered: one or more values are invalid.'),
      502:
        path.endsWith('/refresh') &&
        response.headers.get('Content-Type')?.includes('application/json')
          ? message('The refresh failed. Check the source status and history for details.')
          : message('The server is not responding. Wait a minute and reload the page.'),
    }
    const delay = response.headers.get('Retry-After')
    throw new ApiError(
      response.status === 429
        ? delay && /^\d{1,6}$/.test(delay)
          ? message('Too many refresh requests. Try again in {seconds} seconds.', {
              seconds: delay,
            })
          : message('Too many refresh requests. Try again later.')
        : (messages[response.status] ??
            message('The server could not complete the request. Try again.')),
      response.status,
    )
  }
  if (response.status === 204) return undefined as T
  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(message('The server returned an invalid response.'), response.status)
  }
}

export function mutate<T>(
  path: string,
  method: 'POST' | 'PATCH' | 'DELETE' | 'PUT',
  body?: unknown,
) {
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

export function formatDate(value: string | null, locale = 'it-IT'): string {
  const language = locale.startsWith('en') ? 'en' : 'it'
  if (!value) return translate('Never', language)
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? translate('Date unavailable', language)
    : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function errorMessage(error: unknown): UiMessage {
  return error instanceof ApiError ? error.uiMessage : message('The action failed. Try again.')
}

export interface SourceProposal {
  id: number
  name: string
  url: string | null
  note: string | null
  category_id: number | null
  follow_on_approval: boolean
  status: 'pending' | 'approved' | 'rejected' | 'cancelled'
  created_at: string
  decided_at: string | null
  reason: string | null
  source_id: number | null
  approved_name: string | null
  approved_feed_url: string | null
  user: AppUser
}

export interface BriefArticle {
  category_name?: string
  id: number
  title: string
  url: string
  source: string
  date: string
  date_is_fetched: boolean
  removed: boolean
}
export interface AIBrief {
  id: string
  category_name: string
  generated_at: string
  window_start: string
  window_end: string
  summary: string
  articles: BriefArticle[]
}
export interface BriefState {
  next_edition_at?: string | null
  last_error_code?: string | null
  category_id: number | null
  category_name: string
  code: string
  can_generate: boolean
  retry_at: string | null
  quota_reset_at: string
  attempts_remaining: number
  briefs: AIBrief[]
  articles: BriefArticle[]
  last_job_status: string | null
}
export function briefStatusMessage(code: string): UiMessage {
  const messages: Record<string, UiMessage> = {
    available: message(
      'Ready for an explicit generation request. Availability is checked before sending.',
    ),
    disabled: message('AI generation is not enabled. Saved briefs remain available.'),
    cached: message('A shared brief has already been generated today.'),
    monthly_budget: message(
      'The local monthly budget of USD 2.00 is exhausted. Saved digests remain available.',
    ),
    activation_required: message(
      'Gemini activation is not configured by the operator. Saved digests remain available.',
    ),
    input_limit: message(
      'The selected RSS input exceeds the token limit. No digest was generated.',
    ),
    daily_limit: message(
      'The daily limit has been reached. Generation will be available again when the quota resets',
    ),
    busy: message(
      'Generation is already in progress. Refresh the saved results to check its status.',
    ),
    temporary_limit: message(
      'Temporary limit. Wait until the indicated time before requesting another brief.',
    ),
    model_unavailable: message(
      'Gemini 3.1 Flash-Lite is unavailable. No alternative model will be used.',
    ),
    provider_unavailable: message('The provider is unavailable. No automatic retry will be made.'),
    invalid_output: message('The result could not be validated. The attempt remains counted.'),
    safety_stop: message(
      'AI generation is suspended after a service anomaly. An administrator must review it. Saved briefs remain available.',
    ),
    uncertain: message(
      'The previous attempt has an uncertain outcome. It remains counted and will not be repeated automatically.',
    ),
    category_limit: message('This category has used its two daily attempts.'),
    category_cooldown: message('Wait at least one hour after the category’s failed attempt.'),
    empty: message('No news in the last 24 hours.'),
    insufficient_material: message(
      'Not enough RSS descriptions for a reliable brief. Read the available articles below.',
    ),
  }
  return messages[code] ?? messages.provider_unavailable
}
