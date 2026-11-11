import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../src/App'
import type { SourceProposal } from '../src/api'
import { mockServer } from './server'

const pending: SourceProposal = {
  id: 1,
  name: 'Suggested News',
  url: null,
  note: 'A useful publication',
  category_id: null,
  follow_on_approval: true,
  status: 'pending',
  created_at: '2026-11-09T10:00:00Z',
  decided_at: null,
  reason: null,
  source_id: null,
  approved_name: null,
  approved_feed_url: null,
  user: { id: 'reader', display_name: 'Friend', role: 'reader' },
}
function open() {
  history.replaceState(null, '', '#proposals')
  render(<App />)
}

describe('source proposals', () => {
  it('submits just a name with explicit follow consent and cancels the pending proposal', async () => {
    const { state, calls } = mockServer()
    state.user.role = 'reader'
    state.subscriptions = []
    const user = userEvent.setup()
    open()
    await screen.findByRole('link', { name: 'Proponi una fonte' })
    await screen.findByLabelText('Nome')
    await user.type(screen.getByLabelText('Nome'), 'New publication')
    expect(screen.getByLabelText('Segui questa fonte se approvata')).not.toBeChecked()
    await user.click(screen.getByLabelText('Segui questa fonte se approvata'))
    await user.click(screen.getByRole('button', { name: 'Invia proposta' }))
    await screen.findByRole('heading', { name: 'New publication' })
    expect(calls.find((c) => c.path === '/api/proposals' && c.method === 'POST')?.body).toEqual({
      name: 'New publication',
      url: null,
      note: null,
      category_id: null,
      follow_on_approval: true,
    })
    expect(calls.some((c) => c.path.startsWith('/api/sources') && c.method !== 'GET')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Annulla proposta' }))
    await screen.findByText(/Annullata ·/)
    expect(screen.queryByRole('button', { name: 'Annulla proposta' })).not.toBeInTheDocument()
  })

  it('keeps input on errors and changes language without losing the draft', async () => {
    const { state } = mockServer()
    state.user.role = 'reader'
    state.failProposal = 409
    const user = userEvent.setup()
    open()
    await screen.findByLabelText('Nome')
    await user.type(screen.getByLabelText('Nome'), 'Draft')
    await user.click(screen.getByRole('button', { name: 'Invia proposta' }))
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await user.selectOptions(screen.getByLabelText('Lingua'), 'en')
    expect(screen.getByLabelText('Name')).toHaveValue('Draft')
    expect(screen.getByRole('button', { name: 'Send proposal' })).toBeInTheDocument()
  })

  it('requires explicit approval and sends a corrected feed and category', async () => {
    const { state, calls } = mockServer()
    state.proposals = [structuredClone(pending)]
    const user = userEvent.setup()
    open()
    await screen.findByRole('link', { name: 'Proposte (1)' })
    await user.click(await screen.findByRole('button', { name: 'Valuta proposta' }))
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    await user.clear(screen.getByLabelText('Nome'))
    await user.type(screen.getByLabelText('Nome'), 'Corrected news')
    await user.type(screen.getByLabelText('URL del feed RSS/Atom'), 'https://example.org/feed')
    await user.selectOptions(screen.getByLabelText('Categoria suggerita'), '1')
    await user.click(screen.getByRole('button', { name: 'Approva proposta' }))
    await screen.findByRole('link', { name: 'Proposte (0)' })
    expect(calls.find((c) => c.path.endsWith('/approve'))?.body).toEqual({
      name: 'Corrected news',
      feed_url: 'https://example.org/feed',
      category_id: 1,
    })
  })

  it('links existing sources without editing them and stores rejection reasons', async () => {
    const { state, calls } = mockServer()
    state.proposals = [
      structuredClone(pending),
      { ...structuredClone(pending), id: 2, name: 'Another' },
    ]
    const user = userEvent.setup()
    open()
    await user.click((await screen.findAllByRole('button', { name: 'Valuta proposta' }))[0])
    await user.selectOptions(screen.getByLabelText('Collega una fonte esistente'), '1')
    expect(screen.queryByLabelText('URL del feed RSS/Atom')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approva proposta' }))
    await screen.findByRole('link', { name: 'Proposte (1)' })
    expect(calls.find((c) => c.path.endsWith('/approve'))?.body).toEqual({ source_id: 1 })
    await user.click(screen.getByRole('button', { name: 'Valuta proposta' }))
    await user.type(screen.getByLabelText('Motivazione del rifiuto'), 'No accessible RSS feed')
    await user.click(screen.getByRole('button', { name: 'Rifiuta proposta' }))
    await screen.findByRole('link', { name: 'Proposte (0)' })
    await user.selectOptions(screen.getByLabelText('Stato'), 'rejected')
    await screen.findByText('Motivazione: No accessible RSS feed')
  })

  it('refreshes the persisted count on return without a polling timer', async () => {
    const { state, calls } = mockServer()
    open()
    await screen.findByRole('link', { name: 'Proposte (0)' })
    state.proposals.push(structuredClone(pending))
    act(() => window.dispatchEvent(new Event('focus')))
    await screen.findByRole('link', { name: 'Proposte (1)' })
    const count = calls.filter((c) => c.path.includes('status=pending&limit=1')).length
    act(() => {
      window.dispatchEvent(new Event('focus'))
      window.dispatchEvent(new Event('pageshow'))
    })
    await waitFor(() =>
      expect(calls.filter((c) => c.path.includes('status=pending&limit=1'))).toHaveLength(count),
    )
  })
})
