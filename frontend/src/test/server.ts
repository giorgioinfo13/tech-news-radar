import { vi } from 'vitest'
import type { ReaderUsage } from '../pages/ReaderUsage'
import type {
  AppUser,
  BriefState,
  Article,
  Category,
  CollectionRun,
  ReaderInvitation,
  Source,
  SourceProposal,
} from '../api'

export const category: Category = {
  id: 1,
  name: 'Intelligenza artificiale',
  slug: 'ai',
  sort_order: 0,
}
export const source: Source = {
  id: 1,
  name: 'Example News',
  feed_url: 'https://example.org/feed',
  category_id: 1,
  category,
  enabled: true,
  refresh_interval_minutes: 60,
  last_checked_at: null,
  last_success_at: null,
  last_error: null,
  consecutive_failures: 0,
  created_at: '2026-01-01T00:00:00Z',
}
export const article: Article = {
  id: 1,
  source_id: 1,
  source: { id: 1, name: source.name, category },
  title: 'Una nuova idea per la ricerca',
  description: 'Una descrizione breve e utile.',
  url: 'https://example.org/article',
  published_at: '2026-01-01T12:00:00Z',
  fetched_at: '2026-01-02T00:00:00Z',
  is_read: false,
}

export function mockServer() {
  const state = {
    user: { id: 'owner', display_name: 'Owner', role: 'admin' } as AppUser,
    accessStatus: 200,
    subscriptions: [1],
    failSubscription: 0,
    categories: [structuredClone(category)],
    sources: [structuredClone(source)],
    articles: [structuredClone(article)],
    runs: [] as CollectionRun[],
    failRefresh: 0,
    newsRefresh: {
      checked: 1,
      added: 2,
      failed: 0,
      skipped: 0,
      deferred: 0,
      retry_after: null as number | null,
    },
    failRead: false,
    invitations: [] as ReaderInvitation[],
    failInvitation: 0,
    readerUsage: [] as ReaderUsage[],
    proposals: [] as SourceProposal[],
    failProposal: 0,
    brief: {
      category_id: 1,
      category_name: category.name,
      code: 'available',
      can_generate: true,
      retry_at: null,
      quota_reset_at: '2026-11-10T00:00:00Z',
      attempts_remaining: 16,
      briefs: [],
      articles: [],
      last_job_status: null,
    } as BriefState,
  }
  const calls: {
    path: string
    method: string
    body: Record<string, unknown>
    authorization: string | null
  }[] = []
  function response(body: unknown, status = 200, headers: Record<string, string> = {}) {
    return new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json', ...headers },
    })
  }
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const path = url.pathname.replace('/api', '')
    const method = init?.method ?? 'GET'
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {}
    calls.push({
      path: url.pathname + url.search,
      method,
      body,
      authorization: new Headers(init?.headers).get('Authorization'),
    })
    if (state.accessStatus !== 200) return response({}, state.accessStatus)
    if (path === '/me') return response(state.user)
    const id = Number(path.split('/')[2])
    if (path === '/briefs/digest' && method === 'GET') {
      return response({ ...state.brief, category_id: null })
    }
    if (path.startsWith('/proposals') && method === 'POST') {
      if (state.failProposal) return response({}, state.failProposal)
      if (path === '/proposals') {
        const proposal = {
          id: state.proposals.length + 1,
          name: String(body.name),
          url: body.url ?? null,
          note: body.note ?? null,
          category_id: body.category_id ?? null,
          follow_on_approval: body.follow_on_approval ?? false,
          status: 'pending',
          created_at: '2026-11-09T10:00:00Z',
          decided_at: null,
          reason: null,
          source_id: null,
          approved_name: null,
          approved_feed_url: null,
          user: { ...state.user },
        } as SourceProposal
        state.proposals.unshift(proposal)
        return response(proposal, 201)
      }
      const proposal = state.proposals.find((p) => p.id === id)!
      proposal.status = path.endsWith('/approve')
        ? 'approved'
        : path.endsWith('/reject')
          ? 'rejected'
          : 'cancelled'
      proposal.reason = body.reason ? String(body.reason) : null
      proposal.decided_at = '2026-11-09T11:00:00Z'
      return response(proposal)
    }
    if (path.startsWith('/invitations') && method !== 'GET') {
      if (state.failInvitation) return response({}, state.failInvitation)
      if (method === 'POST') {
        const email = String(body.email).toLowerCase()
        if (state.invitations.some((item) => item.email === email)) return response({}, 409)
        const invitation: ReaderInvitation = {
          id: crypto.randomUUID(),
          email,
          display_name: String(body.display_name),
          created_at: '2026-01-01T00:00:00Z',
          accepted_at: null,
        }
        state.invitations.unshift(invitation)
        return response(invitation, 201)
      }
      const invitation = state.invitations.find((item) => item.id === path.split('/')[2])
      if (!invitation || invitation.accepted_at) return response({}, 409)
      state.invitations = state.invitations.filter((item) => item.id !== invitation.id)
      return response(null, 204)
    }
    if (method === 'GET') {
      let items: unknown[]
      if (path === '/subscriptions')
        items = state.sources
          .filter((item) => state.subscriptions.includes(item.id))
          .map((item) => ({ source_id: item.id, source: item, created_at: '2026-01-01T00:00:00Z' }))
      else if (path === '/categories') items = state.categories
      else if (path === '/proposals')
        items = state.proposals.filter(
          (p) =>
            (!url.searchParams.get('status') || p.status === url.searchParams.get('status')) &&
            (state.user.role === 'admin' || p.user.id === state.user.id),
        )
      else if (path === '/invitations') items = state.invitations
      else if (path === '/usage/readers') items = state.readerUsage
      else if (path === '/sources') items = state.sources
      else if (path.endsWith('/runs')) items = state.runs.filter((run) => run.source_id === id)
      else if (path === '/articles') {
        items = state.articles.filter(
          (item) =>
            state.subscriptions.includes(item.source_id) &&
            (!url.searchParams.has('source_id') ||
              item.source_id === Number(url.searchParams.get('source_id'))) &&
            (!url.searchParams.has('category_id') ||
              item.source.category?.id === Number(url.searchParams.get('category_id'))) &&
            (!url.searchParams.has('is_read') ||
              item.is_read === (url.searchParams.get('is_read') === 'true')) &&
            (!url.searchParams.get('q') ||
              item.title.toLowerCase().includes(url.searchParams.get('q')!.toLowerCase())),
        )
      } else return response({}, 404)
      const offset = Number(url.searchParams.get('offset') ?? 0)
      const limit = Number(url.searchParams.get('limit') ?? 50)
      return response({
        items: items.slice(offset, offset + limit),
        total: items.length,
        limit,
        offset,
      })
    }
    if (path.startsWith('/subscriptions/')) {
      if (id === state.failSubscription) return response({}, 500)
      if (method === 'PUT' && !state.subscriptions.includes(id)) state.subscriptions.push(id)
      if (method === 'DELETE')
        state.subscriptions = state.subscriptions.filter((value) => value !== id)
      return response(null, 204)
    }
    if (path === '/sources/refresh') {
      if (state.failRefresh) return response({}, state.failRefresh, { 'Retry-After': '900' })
      return response(state.newsRefresh)
    }
    if (path.endsWith('/refresh')) {
      if (state.failRefresh === 429) return response({}, 429, { 'Retry-After': '42' })
      const run: CollectionRun = {
        id: state.runs.length + 1,
        source_id: id,
        started_at: '2026-01-03T00:00:00Z',
        finished_at: '2026-01-03T00:00:01Z',
        status: state.failRefresh ? 'error' : 'success',
        articles_seen: 3,
        articles_added: state.failRefresh ? 0 : 2,
        error_message: state.failRefresh ? 'Feed request timed out' : null,
      }
      state.runs.unshift(run)
      Object.assign(
        state.sources.find((item) => item.id === id)!,
        { last_checked_at: run.finished_at, last_error: run.error_message },
      )
      return response(run, state.failRefresh || 200)
    }
    if (path.startsWith('/articles/') && method === 'PATCH') {
      if (state.failRead) return response({}, 500)
      const item = state.articles.find((item) => item.id === id)!
      Object.assign(item, body)
      return response(item)
    }
    if (path.startsWith('/sources')) {
      if (method === 'POST') {
        const item = {
          ...source,
          ...body,
          id: Math.max(0, ...state.sources.map((item) => item.id)) + 1,
        } as Source
        item.category =
          state.categories.find((category) => category.id === item.category_id) ?? null
        state.sources.push(item)
        return response(item, 201)
      }
      if (method === 'PATCH') {
        const item = state.sources.find((item) => item.id === id)!
        Object.assign(item, body)
        item.category =
          state.categories.find((category) => category.id === item.category_id) ?? null
        return response(item)
      }
      if (method === 'DELETE') {
        state.sources = state.sources.filter((item) => item.id !== id)
        return response(null, 204)
      }
    }
    if (path.startsWith('/categories')) {
      if (method === 'POST') {
        const item = {
          ...body,
          id: Math.max(0, ...state.categories.map((item) => item.id)) + 1,
        } as Category
        state.categories.push(item)
        return response(item, 201)
      }
      if (method === 'PATCH') {
        const item = state.categories.find((item) => item.id === id)!
        Object.assign(item, body)
        return response(item)
      }
      if (method === 'DELETE') {
        state.categories = state.categories.filter((item) => item.id !== id)
        return response(null, 204)
      }
    }
    return response({}, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { state, calls, fetchMock, response }
}
