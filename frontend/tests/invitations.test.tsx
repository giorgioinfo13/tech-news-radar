import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../src/App'
import { mockServer } from './server'

function open() {
  history.replaceState(null, '', '#invitations')
  render(<App />)
}

describe('admin invitations', () => {
  it('shows reader usage and refreshes the current counts', async () => {
    const { state } = mockServer()
    state.readerUsage = [
      {
        id: 'reader',
        display_name: 'Usage reader',
        created_at: '2026-01-01T00:00:00Z',
        last_seen_at: new Date().toISOString(),
        followed_sources: 2,
        read_articles: 3,
        last_read_at: null,
      },
    ]
    open()
    await screen.findByText('Usage reader')
    expect(screen.getByText(/Autorizzati: 1 · Rilevati in 7 giorni: 1/)).toBeInTheDocument()
    expect(
      screen.getByText(/Fonti seguite: 2 · Articoli attualmente segnati come letti: 3/),
    ).toBeInTheDocument()
    state.readerUsage = []
    await userEvent.setup().click(screen.getByRole('button', { name: 'Aggiorna utilizzo' }))
    await screen.findByText('Non ci sono ancora lettori autorizzati.')
  })
  it('creates and cancels a pending invitation before any sources are selected', async () => {
    const { state, calls } = mockServer()
    state.subscriptions = []
    const user = userEvent.setup()
    open()
    await screen.findByRole('heading', { name: 'Invita un lettore' })
    await user.type(screen.getByLabelText('Nome'), 'Friend')
    await user.type(screen.getByLabelText('Email Google'), 'Friend@example.org')
    await user.click(screen.getByRole('button', { name: 'Salva invito' }))
    await screen.findByText('friend@example.org')
    expect(screen.getByLabelText('Email Google')).toHaveValue('')
    expect(screen.getByText(/Non viene inviata un’email automatica/)).toBeInTheDocument()
    expect(
      calls.some((call) => call.method === 'POST' && call.body.display_name === 'Friend'),
    ).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Annulla invito per friend@example.org' }))
    await screen.findByRole('heading', { name: 'Il prossimo lettore lo scegli tu' })
    expect(state.invitations).toHaveLength(0)
  })

  it('preserves input on duplicate or unavailable service and lets the admin retry', async () => {
    const { state } = mockServer()
    const user = userEvent.setup()
    open()
    await screen.findByLabelText('Nome')
    await user.type(screen.getByLabelText('Nome'), 'Friend')
    await user.type(screen.getByLabelText('Email Google'), 'friend@example.org')
    for (const status of [409, 503]) {
      state.failInvitation = status
      await user.click(screen.getByRole('button', { name: 'Salva invito' }))
      expect(await screen.findByRole('alert')).toBeInTheDocument()
      expect(screen.getByLabelText('Email Google')).toHaveValue('friend@example.org')
      expect(state.invitations).toHaveLength(0)
    }
    state.failInvitation = 0
    await user.click(screen.getByRole('button', { name: 'Salva invito' }))
    await screen.findByText('friend@example.org')
  })

  it('paginates and keeps used invitations read-only', async () => {
    const { state } = mockServer()
    state.invitations = Array.from({ length: 21 }, (_, id) => ({
      id: String(id),
      email: `friend${id}@example.org`,
      display_name: `Friend ${id}`,
      created_at: '2026-01-01T00:00:00Z',
      accepted_at: id === 0 ? '2026-01-02T00:00:00Z' : null,
    }))
    const user = userEvent.setup()
    open()
    const accepted = (await screen.findByText('friend0@example.org')).closest('article')!
    expect(within(accepted).getByText(/Utilizzato/)).toBeInTheDocument()
    expect(within(accepted).queryByRole('button')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Successivi' }))
    await screen.findByText('friend20@example.org')
    await user.click(
      screen.getByRole('button', { name: 'Annulla invito per friend20@example.org' }),
    )
    await screen.findByText('friend0@example.org')
    expect(screen.getByRole('button', { name: 'Precedenti' })).toBeDisabled()
  })

  it('never requests invitations for a reader, even with a direct hash URL', async () => {
    const { state, calls } = mockServer()
    state.user.role = 'reader'
    open()
    await screen.findByRole('link', { name: /Una nuova idea/ })
    expect(screen.queryByRole('link', { name: 'Inviti' })).not.toBeInTheDocument()
    await waitFor(() =>
      expect(calls.some((call) => call.path.startsWith('/api/articles'))).toBe(true),
    )
    expect(calls.some((call) => call.path.startsWith('/api/invitations'))).toBe(false)
    expect(calls.some((call) => call.path.startsWith('/api/usage'))).toBe(false)
  })
})
