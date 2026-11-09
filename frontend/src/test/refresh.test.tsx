import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import { mockServer } from './server'

function pull(element: Element, distance = 110, x = 150) {
  fireEvent.touchStart(element, { touches: [{ clientX: x, clientY: 100 }] })
  fireEvent.touchMove(element, { touches: [{ clientX: x, clientY: 100 + distance }] })
  fireEvent.touchEnd(element)
}

async function open() {
  history.replaceState(null, '', '#news')
  const view = render(<App />)
  await screen.findByRole('link', { name: /Una nuova idea/ })
  return { ...view, surface: document.querySelector('.news-refresh-surface')! }
}

describe('RSS refresh from news', () => {
  it('runs only on request, preserves filters and reading state, and reloads the database', async () => {
    const { state, calls } = mockServer()
    const user = userEvent.setup()
    await open()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
    await user.click(screen.getByRole('button', { name: /Segna come letto:/ }))
    await screen.findByRole('button', { name: /Segna da leggere:/ })
    await user.selectOptions(screen.getByLabelText('Fonte'), '1')
    await user.click(screen.getByRole('button', { name: 'Lette' }))
    await screen.findByRole('link', { name: /Una nuova idea/ })
    const button = screen.getByRole('button', { name: 'Aggiorna fonti' })
    button.focus()
    await user.keyboard('{Enter}')
    await screen.findByText(/Nuovi articoli: 2 · Fonti controllate: 1/)
    await waitFor(() => expect(calls.at(-1)?.path).toContain('/articles?'))
    expect(calls.at(-1)?.path).toContain('source_id=1&is_read=true')
    expect(state.articles[0].is_read).toBe(true)
    expect(calls.filter((call) => call.method === 'POST').map((call) => call.path)).toEqual([
      '/api/sources/refresh',
    ])
    expect(screen.getByLabelText('Fonte')).toHaveValue('1')
    expect(calls.some((call) => /internal|briefs|gemini/.test(call.path))).toBe(false)
  })

  it('shares the request for the gesture and button and prevents repeated input', async () => {
    const server = mockServer()
    const { surface } = await open()
    let complete!: (response: Response) => void
    server.fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve
        }),
    )
    pull(surface)
    await screen.findByRole('button', { name: 'Aggiornamento fonti…' })
    expect(screen.getByRole('button', { name: 'Aggiornamento fonti…' })).toBeDisabled()
    pull(surface)
    fireEvent.click(screen.getByRole('button', { name: 'Aggiornamento fonti…' }))
    expect(
      server.fetchMock.mock.calls.filter(([path]) => path === '/api/sources/refresh'),
    ).toHaveLength(1)
    await act(async () => complete(server.response(server.state.newsRefresh)))
    await screen.findByText(/Nuovi articoli: 2/)
    pull(surface)
    expect(
      server.fetchMock.mock.calls.filter(([path]) => path === '/api/sources/refresh'),
    ).toHaveLength(1)
  })

  it('ignores short, horizontal, cancelled, multi-touch, edge and scrolled gestures', async () => {
    const { calls } = mockServer()
    const { surface } = await open()
    pull(surface, 50)
    pull(surface, 120, 5)
    vi.stubGlobal('scrollY', 50)
    pull(surface)
    vi.stubGlobal('scrollY', 0)
    fireEvent.touchStart(surface, { touches: [{ clientX: 150, clientY: 100 }] })
    fireEvent.touchMove(surface, { touches: [{ clientX: 300, clientY: 200 }] })
    fireEvent.touchEnd(surface)
    fireEvent.touchStart(surface, { touches: [{ clientX: 150, clientY: 100 }] })
    fireEvent.touchMove(surface, { touches: [{ clientX: 150, clientY: 210 }] })
    expect(screen.getByText('Rilascia per aggiornare le fonti')).toBeInTheDocument()
    fireEvent.touchCancel(surface)
    fireEvent.touchEnd(surface)
    fireEvent.touchStart(surface, {
      touches: [
        { clientX: 150, clientY: 100 },
        { clientX: 160, clientY: 100 },
      ],
    })
    fireEvent.touchEnd(surface)
    pull(screen.getByLabelText('Cerca nelle notizie'))
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
  })

  it('cancels native refresh only during the downward gesture and cleans up on exit', async () => {
    mockServer()
    const { surface, unmount } = await open()
    fireEvent.touchStart(surface, { touches: [{ clientX: 150, clientY: 100 }] })
    const move = new Event('touchmove', { cancelable: true, bubbles: true })
    Object.defineProperty(move, 'touches', { value: [{ clientX: 150, clientY: 140 }] })
    fireEvent(surface, move)
    expect(move.defaultPrevented).toBe(true)
    expect(document.documentElement).toHaveClass('news-pull-refresh')
    unmount()
    expect(document.documentElement).not.toHaveClass('news-pull-refresh')
  })

  it('shows partial results and failures without automatic retries', async () => {
    const { state, calls } = mockServer()
    state.newsRefresh = {
      checked: 2,
      added: 1,
      failed: 1,
      skipped: 3,
      deferred: 5,
      retry_after: null,
    }
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Aggiorna fonti' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Aggiornamento parziale: restano 5 fonti',
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Non riuscite: 1')
    await waitFor(() => expect(calls.at(-1)?.path).toContain('/articles?'))
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
  })

  it.each([409, 429, 500])(
    'reloads saved articles and reports HTTP %s honestly',
    async (status) => {
      const { state, calls } = mockServer()
      state.failRefresh = status
      await open()
      fireEvent.click(screen.getByRole('button', { name: 'Aggiorna fonti' }))
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(
        status === 409
          ? 'Una raccolta è già in corso'
          : status === 429
            ? '900 secondi'
            : 'Il server non ha completato',
      )
      await waitFor(() => expect(calls.at(-1)?.path).toContain('/articles?'))
      expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
    },
  )

  it.each(['it', 'en'])(
    'reports recent sources in %s and reloads without resetting filters',
    async (language) => {
      const { state, calls } = mockServer()
      localStorage.setItem('tnr-language', language)
      state.newsRefresh = {
        checked: 0,
        added: 0,
        failed: 0,
        skipped: 3,
        deferred: 0,
        retry_after: 840,
      }
      await open()
      fireEvent.click(
        screen.getByRole('button', {
          name: language === 'it' ? 'Aggiorna fonti' : 'Refresh sources',
        }),
      )
      await screen.findByText(language === 'it' ? /controllate di recente/ : /checked recently/)
      await waitFor(() => expect(calls.at(-1)?.path).toContain('/articles?'))
    },
  )

  it('reports an unconfirmed result after connection loss without retrying the POST', async () => {
    const server = mockServer()
    await open()
    server.fetchMock.mockRejectedValueOnce(new TypeError('connection lost'))
    fireEvent.click(screen.getByRole('button', { name: 'Aggiorna fonti' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Esito non confermato')
    await waitFor(() => expect(server.calls.at(-1)?.path).toContain('/articles?'))
    expect(
      server.fetchMock.mock.calls.filter(([path]) => path === '/api/sources/refresh'),
    ).toHaveLength(1)
  })
})
