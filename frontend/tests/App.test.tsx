import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../src/App'
import { article, category, mockServer, source } from './server'

function open(page: string) {
  history.replaceState(null, '', `#${page === 'sources' ? 'catalog' : page}`)
  return render(<App />)
}

describe('news dashboard', () => {
  it('shows a separate safe Hacker News discussion link', async () => {
    const { state } = mockServer()
    state.articles = [
      { ...article, description: null, discussion_url: 'https://news.ycombinator.com/item?id=123' },
    ]
    open('news')
    const link = await screen.findByRole('link', { name: 'Discussione su Hacker News' })
    expect(link).toHaveAttribute('href', 'https://news.ycombinator.com/item?id=123')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.queryByText('Comments')).not.toBeInTheDocument()
  })
  it('loads articles, combines filters and searches only on submit', async () => {
    const { calls } = mockServer()
    const user = userEvent.setup()
    open('news')
    expect(await screen.findByRole('link', { name: /Una nuova idea/ })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    )
    await user.selectOptions(screen.getByLabelText('Fonte'), '1')
    await user.selectOptions(screen.getByLabelText('Categoria'), '1')
    await user.click(screen.getByRole('button', { name: 'Da leggere' }))
    await user.type(screen.getByLabelText('Cerca nelle notizie'), 'ricerca')
    expect(calls.some((call) => call.path.includes('q='))).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Cerca' }))
    await waitFor(() => expect(calls.at(-1)?.path).toContain('q=ricerca'))
    expect(calls.at(-1)?.path).toContain('source_id=1&is_read=false')
    expect(calls.at(-1)?.path).toContain('category_id=1')
    await user.click(screen.getByRole('button', { name: 'Azzera filtri' }))
    expect(screen.getByLabelText('Cerca nelle notizie')).toHaveValue('')
  })

  it('paginates and returns to the first page after changing a filter', async () => {
    const { state, calls } = mockServer()
    state.articles = Array.from({ length: 21 }, (_, index) => ({
      ...article,
      id: index + 1,
      title: `Notizia ${index + 1}`,
    }))
    const user = userEvent.setup()
    open('news')
    await screen.findByRole('link', { name: 'Notizia 1' })
    await user.click(screen.getByRole('button', { name: 'Successivi' }))
    await screen.findByRole('link', { name: 'Notizia 21' })
    expect(screen.queryByRole('link', { name: 'Notizia 1' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Da leggere' }))
    await screen.findByRole('link', { name: 'Notizia 1' })
    expect(calls.at(-1)?.path).toContain('offset=0')
  })

  it('persists read status and keeps the article unchanged after a failed mutation', async () => {
    const { state } = mockServer()
    const user = userEvent.setup()
    open('news')
    await user.click(await screen.findByRole('button', { name: /Segna come letto:/ }))
    expect(await screen.findByRole('button', { name: /Segna da leggere:/ })).toBeEnabled()
    expect(state.articles[0].is_read).toBe(true)
    state.failRead = true
    await user.click(screen.getByRole('button', { name: /Segna da leggere:/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Il server non ha completato')
    expect(state.articles[0].is_read).toBe(true)
  })

  it('updates the current filter even if it changed while read status was being saved', async () => {
    const server = mockServer()
    server.state.articles = Array.from({ length: 21 }, (_, index) => ({
      ...article,
      id: index + 1,
      title: `Notizia ${index + 1}`,
    }))
    const user = userEvent.setup()
    open('news')
    await screen.findByRole('link', { name: 'Notizia 1' })
    await user.click(screen.getByRole('button', { name: 'Da leggere' }))
    await screen.findByRole('link', { name: 'Notizia 1' })
    await user.click(screen.getByRole('button', { name: 'Successivi' }))
    await screen.findByRole('link', { name: 'Notizia 21' })
    let complete!: (response: Response) => void
    server.fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          complete = resolve
        }),
    )
    await user.click(screen.getByRole('button', { name: 'Segna come letto: Notizia 21' }))
    await user.click(screen.getByRole('button', { name: 'Lette' }))
    await screen.findByRole('heading', { name: 'Nessuna notizia da mostrare' })
    server.state.articles[20].is_read = true
    await act(async () => complete(server.response(server.state.articles[20])))
    expect(await screen.findByRole('link', { name: 'Notizia 21' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Precedenti' })).toBeDisabled()
  })

  it('shows empty states and retries a failed initial load', async () => {
    const { state, fetchMock } = mockServer()
    state.sources = []
    state.articles = []
    fetchMock.mockRejectedValueOnce(new TypeError('Network error'))
    const user = userEvent.setup()
    open('news')
    expect(await screen.findByRole('alert')).toHaveTextContent('Impossibile contattare')
    await user.click(screen.getByRole('button', { name: 'Riprova' }))
    await user.click(await screen.findByRole('button', { name: 'Non ora' }))
    expect(
      await screen.findByRole('heading', { name: 'Il tuo radar parte da una fonte' }),
    ).toBeInTheDocument()
  })

  it('renders untrusted content as text and refuses unsafe article links', async () => {
    const { state } = mockServer()
    state.articles[0] = {
      ...article,
      title: '<script>evil()</script>',
      description: '<img src=x onerror=evil()>',
      url: 'javascript:evil()',
    }
    open('news')
    expect(
      await screen.findByRole('heading', { name: '<script>evil()</script>' }),
    ).toBeInTheDocument()
    expect(screen.getByText('<img src=x onerror=evil()>')).toBeInTheDocument()
    expect(
      document.querySelector('.article-card img, .article-card script, .article-card h3 a'),
    ).toBeNull()
  })

  it('ignores late responses from obsolete filters', async () => {
    const server = mockServer()
    const user = userEvent.setup()
    open('news')
    await screen.findByRole('link', { name: /Una nuova idea/ })
    let resolve!: (response: Response) => void
    server.fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((done) => {
          resolve = done
        }),
    )
    await user.click(screen.getByRole('button', { name: 'Da leggere' }))
    await user.click(screen.getByRole('button', { name: 'Lette' }))
    await screen.findByRole('heading', { name: 'Nessuna notizia da mostrare' })
    await act(async () =>
      resolve(server.response({ items: [article], total: 1, limit: 20, offset: 0 })),
    )
    expect(screen.queryByRole('link', { name: /Una nuova idea/ })).not.toBeInTheDocument()
  })
})

describe('source management', () => {
  it('creates, edits, uncategorizes and disables a source', async () => {
    const { state } = mockServer()
    const user = userEvent.setup()
    open('sources')
    await user.click(await screen.findByRole('button', { name: 'Aggiungi fonte' }))
    await user.type(screen.getByLabelText('Nome della fonte'), 'Nuovo feed')
    await user.type(screen.getByLabelText('URL del feed'), 'https://news.example/rss')
    await user.selectOptions(screen.getByLabelText('Categoria'), '1')
    await user.click(screen.getByRole('button', { name: 'Salva fonte' }))
    await screen.findByRole('heading', { name: 'Nuovo feed' })
    expect(state.sources[1].category_id).toBe(1)
    await user.click(screen.getByRole('button', { name: 'Modifica Nuovo feed' }))
    await user.clear(screen.getByLabelText('Nome della fonte'))
    await user.type(screen.getByLabelText('Nome della fonte'), 'Rinominato')
    await user.selectOptions(screen.getByLabelText('Categoria'), '')
    await user.click(screen.getByRole('button', { name: 'Salva fonte' }))
    await screen.findByRole('heading', { name: 'Rinominato' })
    expect(state.sources[1].category_id).toBeNull()
    await user.click(screen.getByLabelText('Dettagli e azioni Rinominato'))
    await user.click(screen.getByRole('button', { name: 'Disattiva Rinominato' }))
    expect(await screen.findByRole('button', { name: 'Aggiorna Rinominato' })).toBeDisabled()
    await waitFor(() => expect(state.sources[1].enabled).toBe(false))
  })

  it('requires explicit confirmation for source deletion and supports cancellation', async () => {
    const { calls } = mockServer()
    const user = userEvent.setup()
    open('sources')
    await user.click(await screen.findByLabelText('Dettagli e azioni Example News'))
    await user.click(screen.getByRole('button', { name: 'Elimina Example News' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('anche tutti gli articoli e la cronologia')
    await user.click(within(dialog).getByRole('button', { name: 'Annulla' }))
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Elimina Example News' }))
    await user.click(screen.getByRole('button', { name: 'Elimina definitivamente' }))
    await screen.findByRole('heading', { name: 'Da dove vuoi iniziare?' })
    expect(calls.filter((call) => call.method === 'DELETE')).toHaveLength(1)
  })

  it('refreshes sources and displays collection history and diagnostics', async () => {
    const { state } = mockServer()
    const user = userEvent.setup()
    open('sources')
    await user.click(await screen.findByRole('button', { name: 'Aggiorna Example News' }))
    expect(await screen.findByText('Example News: 2 nuovi articoli raccolti.')).toBeInTheDocument()
    await user.click(screen.getByLabelText('Dettagli e azioni Example News'))
    await user.click(screen.getByRole('button', { name: 'Cronologia Example News' }))
    expect(await screen.findByText('Completato')).toBeInTheDocument()
    state.failRefresh = 502
    await user.click(screen.getByRole('button', { name: 'Aggiorna Example News' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Il refresh non è riuscito')
    expect(
      await screen.findByText(/Ultimo aggiornamento non riuscito: Feed request timed out/),
    ).toBeInTheDocument()
    expect(await screen.findByText('Non riuscito')).toBeInTheDocument()
  })

  it('shows Retry-After and keeps form values after API validation errors', async () => {
    const { state, fetchMock, response } = mockServer()
    state.failRefresh = 429
    const user = userEvent.setup()
    open('sources')
    await user.click(await screen.findByRole('button', { name: 'Aggiorna Example News' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('42 secondi')
    await user.click(screen.getByRole('button', { name: 'Modifica Example News' }))
    await user.clear(screen.getByLabelText('Nome della fonte'))
    await user.type(screen.getByLabelText('Nome della fonte'), 'Nome modificato')
    fetchMock.mockResolvedValueOnce(response({}, 409))
    await user.click(screen.getByRole('button', { name: 'Salva fonte' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('duplicati')
    expect(screen.getByLabelText('Nome della fonte')).toHaveValue('Nome modificato')
  })

  it('does not submit unsafe feed URLs', async () => {
    const { calls } = mockServer()
    const user = userEvent.setup()
    open('sources')
    await user.click(await screen.findByRole('button', { name: 'Aggiungi fonte' }))
    await user.type(screen.getByLabelText('Nome della fonte'), 'Unsafe')
    await user.type(screen.getByLabelText('URL del feed'), 'ftp://example.org/file')
    await user.click(screen.getByRole('button', { name: 'Salva fonte' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP o HTTPS')
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
  })
})

describe('categories and navigation', () => {
  it('keeps the current view when skipping to the main content', async () => {
    mockServer()
    open('sources')
    await screen.findByRole('heading', { name: 'Catalogo' })
    act(() => {
      location.hash = '#main-content'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(screen.getByRole('heading', { name: 'Catalogo' })).toBeInTheDocument()
  })
  it('creates and edits a category, then explains deletion semantics', async () => {
    const { state } = mockServer()
    const user = userEvent.setup()
    open('categories')
    await user.click(await screen.findByRole('button', { name: 'Aggiungi categoria' }))
    await user.type(screen.getByLabelText('Nome della categoria'), 'Ricerca')
    await user.type(screen.getByLabelText('Identificativo'), 'ricerca')
    await user.click(screen.getByRole('button', { name: 'Salva categoria' }))
    await screen.findByRole('heading', { name: 'Ricerca' })
    await user.click(screen.getByRole('button', { name: 'Modifica Ricerca' }))
    fireEvent.change(screen.getByLabelText('Ordine'), { target: { value: '-1' } })
    await user.click(screen.getByRole('button', { name: 'Salva categoria' }))
    await waitFor(() => expect(state.categories[1].sort_order).toBe(-1))
    await user.click(screen.getByRole('button', { name: 'Elimina Ricerca' }))
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'Gli articoli e le fonti verranno conservati',
    )
    await user.click(screen.getByRole('button', { name: 'Elimina definitivamente' }))
    await waitFor(() => expect(state.categories).toHaveLength(1))
  })

  it('loads catalogs beyond one API page and responds to hash navigation', async () => {
    const { state, calls } = mockServer()
    state.categories = Array.from({ length: 101 }, (_, index) => ({
      ...category,
      id: index + 1,
      name: `Categoria ${index + 1}`,
      slug: `cat-${index + 1}`,
    }))
    state.sources = [{ ...source, category_id: 101, category: state.categories[100] }]
    open('news')
    expect(await screen.findByRole('option', { name: 'Categoria 101' })).toBeInTheDocument()
    expect(calls.some((call) => call.path === '/api/categories?limit=100&offset=100')).toBe(true)
    act(() => {
      location.hash = '#catalog'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(await screen.findByRole('heading', { name: 'Catalogo' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Catalogo' })).toHaveAttribute('aria-current', 'page')
    act(() => {
      location.hash = ''
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(await screen.findByRole('heading', { name: 'Notizie' })).toBeInTheDocument()
  })
})

describe('editorial interface', () => {
  it('keeps filters when the compact filter panel is closed and reopened', async () => {
    const { calls } = mockServer()
    const user = userEvent.setup()
    open('news')
    await screen.findByRole('link', { name: /Una nuova idea/ })
    const toggle = screen.getByRole('button', { name: /Filtri/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await user.selectOptions(screen.getByLabelText('Fonte'), '1')
    await waitFor(() => expect(calls.at(-1)?.path).toContain('source_id=1'))
    expect(toggle).toHaveTextContent('1 attivo')
    const requests = calls.length
    await user.click(toggle)
    await user.click(toggle)
    expect(screen.getByLabelText('Fonte')).toHaveValue('1')
    expect(calls).toHaveLength(requests)
  })

  it('places editing and history beside the selected source', async () => {
    const { state } = mockServer()
    state.sources.push({
      ...source,
      id: 2,
      name: 'Second source',
      feed_url: 'https://second.example/rss',
    })
    const user = userEvent.setup()
    open('sources')
    const title = await screen.findByRole('heading', { name: 'Second source' })
    const card = title.closest('article')!
    await user.click(screen.getByRole('button', { name: 'Modifica Second source' }))
    expect(within(card).getByLabelText('Nome della fonte')).toHaveValue('Second source')
    expect(within(card).getByRole('region', { name: 'Modifica Second source' })).toHaveFocus()
    await user.click(within(card).getByRole('button', { name: 'Annulla' }))
    expect(screen.getByRole('button', { name: 'Modifica Second source' })).toHaveFocus()
    await user.click(screen.getByLabelText('Dettagli e azioni Second source'))
    await user.click(screen.getByRole('button', { name: 'Cronologia Second source' }))
    expect(
      await within(card).findByRole('region', { name: 'Cronologia · Second source' }),
    ).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Chiudi cronologia' }))
    expect(screen.getByRole('button', { name: 'Cronologia Second source' })).toHaveFocus()
    expect(
      within(card).queryByRole('region', { name: 'Cronologia · Second source' }),
    ).not.toBeInTheDocument()
  })
})
