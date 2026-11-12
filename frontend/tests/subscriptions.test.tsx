import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../src/App'
import { mockServer, source } from './server'

function open() {
  history.replaceState(null, '', '#sources')
  return render(<App />)
}

describe('bulk personal subscriptions', () => {
  it.each(['admin', 'reader'] as const)(
    'lets a %s follow the full catalog and unfollow with confirmation, keeping read history',
    async (role) => {
      const { state, calls } = mockServer()
      state.user.role = role
      state.sources = Array.from({ length: 121 }, (_, index) => ({
        ...source,
        id: index + 1,
        name: `Source ${index + 1}`,
        enabled: index !== 1,
      }))
      state.articles[0].is_read = true
      open()
      await screen.findByText('Fonti seguite: 1 su 121')
      await userEvent.click(screen.getByRole('button', { name: 'Segui tutte' }))
      await screen.findByText('Fonti seguite: 121 su 121')
      expect(screen.getByRole('button', { name: 'Segui tutte' })).toBeDisabled()
      expect(state.subscriptions).toHaveLength(121)
      expect(state.sources[1].enabled).toBe(false)
      expect(screen.getByRole('status')).toHaveTextContent(
        'Fonti aggiunte alle tue iscrizioni: 120.',
      )
      expect(calls.filter((call) => call.method === 'PUT')).toEqual([
        expect.objectContaining({ path: '/api/subscriptions', body: {} }),
      ])

      await userEvent.click(screen.getByRole('button', { name: 'Non seguire più nessuna' }))
      let dialog = screen.getByRole('dialog', { name: 'Non seguire più nessuna fonte?' })
      expect(dialog).toHaveTextContent('tutte le 121 fonti')
      await userEvent.click(within(dialog).getByRole('button', { name: 'Annulla' }))
      expect(calls.filter((call) => call.method === 'DELETE')).toHaveLength(0)
      await userEvent.click(screen.getByRole('button', { name: 'Non seguire più nessuna' }))
      dialog = screen.getByRole('dialog')
      await userEvent.click(within(dialog).getByRole('button', { name: 'Non seguire più nessuna' }))
      await screen.findByText('Fonti seguite: 0 su 121')
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Non seguire più nessuna' })).toBeDisabled()
      expect(screen.getByRole('status')).toHaveTextContent('Iscrizioni rimosse: 121.')
      expect(state.subscriptions).toEqual([])
      expect(state.articles[0].is_read).toBe(true)
      expect(calls.filter((call) => call.method === 'DELETE')).toHaveLength(1)
      expect(calls.some((call) => call.path.endsWith('/refresh'))).toBe(false)
      // An intentionally empty choice stays on My sources during this session.
      expect(screen.getByRole('heading', { name: 'Le mie fonti' })).toBeInTheDocument()
    },
  )

  it.each(['PUT', 'DELETE'])('shows a failed %s without changing follows', async (method) => {
    const { state } = mockServer()
    state.sources.push({ ...source, id: 2, name: 'Second source' })
    state.failBulkSubscription = 500
    open()
    await screen.findByText('Fonti seguite: 1 su 2')
    if (method === 'PUT') await userEvent.click(screen.getByRole('button', { name: 'Segui tutte' }))
    else {
      await userEvent.click(screen.getByRole('button', { name: 'Non seguire più nessuna' }))
      await userEvent.click(
        within(screen.getByRole('dialog')).getByRole('button', { name: 'Non seguire più nessuna' }),
      )
    }
    expect(await screen.findByRole('alert')).toHaveTextContent('non ha completato')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Segui tutte' })).toBeEnabled())
    expect(state.subscriptions).toEqual([1])
    expect(screen.getByText('Fonti seguite: 1 su 2')).toBeInTheDocument()
  })

  it('disables competing actions while saving and while reloading follows', async () => {
    const server = mockServer()
    server.state.sources.push({ ...source, id: 2, name: 'Second source' })
    open()
    await screen.findByText('Fonti seguite: 1 su 2')
    let complete!: (response: Response) => void
    let reload!: (response: Response) => void
    server.fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve
        }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Segui tutte' }))
    expect(screen.getByRole('button', { name: 'Segui tutte' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Non seguire più nessuna' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Segui Second source' })).toBeDisabled()
    server.fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          reload = resolve
        }),
    )
    await act(async () => complete(server.response({ changed: 1 })))
    expect(screen.getByRole('button', { name: 'Non seguire più nessuna' })).toBeDisabled()
    await act(async () =>
      reload(
        server.response({
          items: server.state.sources.map((item) => ({
            source_id: item.id,
            source: item,
            created_at: source.created_at,
          })),
          total: 2,
          limit: 100,
          offset: 0,
        }),
      ),
    )
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Non seguire più nessuna' })).toBeEnabled(),
    )
  })

  it('reloads after a lost response instead of reporting an unconfirmed success', async () => {
    const server = mockServer()
    server.state.sources.push({ ...source, id: 2, name: 'Second source' })
    open()
    await screen.findByText('Fonti seguite: 1 su 2')
    server.fetchMock.mockImplementationOnce(async () => {
      server.state.subscriptions = [1, 2]
      throw new TypeError('connection lost after commit')
    })
    await userEvent.click(screen.getByRole('button', { name: 'Segui tutte' }))
    await screen.findByText('Fonti seguite: 2 su 2')
    expect(screen.getByRole('alert')).toHaveTextContent('confermato')
    expect(screen.queryByText(/Fonti aggiunte alle tue iscrizioni/)).not.toBeInTheDocument()
  })

  it('selects and deselects every initial choice including paused sources without writing', async () => {
    const { state, calls } = mockServer()
    state.subscriptions = []
    state.sources.push({ ...source, id: 2, name: 'Paused source', enabled: false })
    open()
    await screen.findByText('Fonti selezionate: 1 su 2')
    await userEvent.click(screen.getByRole('button', { name: 'Seleziona tutte' }))
    expect(screen.getByText('Fonti selezionate: 2 su 2')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Paused source/ })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Seleziona tutte' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Deseleziona tutte' }))
    expect(screen.getByText('Fonti selezionate: 0 su 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deseleziona tutte' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Segui 0 fonti e continua' })).toBeDisabled()
    expect(calls.every((call) => call.method === 'GET')).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Non ora' }))
    await screen.findByRole('heading', { name: 'Notizie' })
    expect(state.subscriptions).toEqual([])
  })

  it('disables initial bulk choices when the catalog is empty', async () => {
    const { state } = mockServer()
    state.sources = []
    state.subscriptions = []
    open()
    await screen.findByText('Fonti selezionate: 0 su 0')
    expect(screen.getByRole('button', { name: 'Seleziona tutte' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Deseleziona tutte' })).toBeDisabled()
  })

  it('translates the controls, confirmation and result into English', async () => {
    mockServer()
    localStorage.setItem('tnr-language', 'en')
    open()
    await screen.findByText('You follow 1 of 1 sources')
    await userEvent.click(screen.getByRole('button', { name: 'Unfollow all' }))
    const dialog = screen.getByRole('dialog', { name: 'Unfollow all sources?' })
    expect(dialog).toHaveTextContent('Your reading history will be kept.')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Unfollow all' }))
    await screen.findByText('You follow 0 of 1 sources')
    expect(screen.getByRole('status')).toHaveTextContent('Sources unfollowed: 1.')
  })
})
