import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../src/App'
import { usageData } from './gemini-usage-data'
import { mockServer } from './server'

function setup(role: 'admin' | 'reader' = 'admin') {
  const server = mockServer()
  server.state.user.role = role
  const data = usageData()
  const requests: URL[] = []
  const base = server.fetchMock.getMockImplementation()!
  let status = 200
  server.fetchMock.mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname === '/api/usage/gemini') {
      requests.push(url)
      return new Response(JSON.stringify(data), { status })
    }
    return base(input, init)
  })
  history.replaceState(null, '', '#gemini-usage')
  render(<App />)
  return {
    ...server,
    data,
    requests,
    fail: (value: number) => {
      status = value
    },
  }
}

describe('administrator Gemini statistics', () => {
  it('shows measured tokens, costs and unknown attempts without generating', async () => {
    const { requests, calls } = setup()
    const monthly = await screen.findByRole('region', { name: 'Riepilogo mensile' })
    expect(monthly).toHaveTextContent('Tentativi: 2 · Rassegne salvate: 1 · Consumi verificati: 1')
    expect(monthly).toHaveTextContent('Token totali1200')
    expect(monthly).toHaveTextContent('0,000800')
    expect(monthly).toHaveTextContent('Non disponibili: 1')
    expect(monthly).toHaveTextContent('non fatture o saldi di credito')
    const details = screen
      .getByText(/Rassegna salvata$/, { selector: 'summary span' })
      .closest('details')!
    await userEvent.click(within(details).getByText(/Rassegna salvata$/))
    expect(details).toHaveAttribute('open')
    expect(details).toHaveTextContent('gemini-3.1-flash-lite')
    expect(details).toHaveTextContent('Token di ragionamento100')
    expect(details).toHaveTextContent('Conteggio preventivo di input800')
    const failed = screen
      .getByText('Consumo non disponibile', { selector: 'summary span' })
      .closest('details')!
    await userEvent.click(
      within(failed).getByText('Consumo non disponibile', { selector: 'summary span' }),
    )
    expect(failed).toHaveTextContent('Token totaliNon disponibile')
    expect(failed).toHaveTextContent('Escluso dai totali')
    expect(requests).toHaveLength(1)
    expect(calls.every((call) => call.method === 'GET')).toBe(true)
    expect(calls.some((call) => call.path.includes('/briefs'))).toBe(false)
  })
  it('hides navigation and direct access for a reader without requesting statistics', async () => {
    const { requests } = setup('reader')
    await screen.findByRole('link', { name: 'Le mie fonti' })
    expect(screen.queryByRole('link', { name: 'Statistiche Gemini' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Statistiche Gemini' })).not.toBeInTheDocument()
    expect(requests).toHaveLength(0)
  })
  it('refreshes, paginates and resets the page when the month changes', async () => {
    const { data, requests } = setup()
    data.attempts.total = 21
    await screen.findByRole('region', { name: 'Riepilogo mensile' })
    await userEvent.click(screen.getByRole('button', { name: 'Successivi' }))
    await waitFor(() => expect(requests.at(-1)?.searchParams.get('offset')).toBe('20'))
    fireEvent.change(screen.getByLabelText('Mese (UTC)'), { target: { value: '2026-10' } })
    await waitFor(() => expect(requests.at(-1)?.searchParams.get('month')).toBe('2026-10-01'))
    expect(requests.at(-1)?.searchParams.get('offset')).toBe('0')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Aggiorna statistiche' })).toBeEnabled(),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Aggiorna statistiche' }))
    await waitFor(() => expect(requests).toHaveLength(4))
  })
  it('shows retry after a failed refresh without presenting stale statistics', async () => {
    const { fail } = setup()
    await screen.findByRole('region', { name: 'Riepilogo mensile' })
    fail(500)
    await userEvent.click(screen.getByRole('button', { name: 'Aggiorna statistiche' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('non ha completato')
    expect(screen.queryByRole('region', { name: 'Riepilogo mensile' })).not.toBeInTheDocument()
    fail(200)
    await userEvent.click(screen.getByRole('button', { name: 'Riprova' }))
    await screen.findByRole('region', { name: 'Riepilogo mensile' })
  })
  it('keeps reservations visible when the historical attempts are unavailable', async () => {
    const { data } = setup()
    data.attempts = { total: 0, items: [], limit: 20, offset: 0 }
    data.days = []
    data.summary = {
      ...data.summary,
      attempts: 0,
      successes: 0,
      measured_attempts: 0,
      unavailable_attempts: 0,
      input_tokens: 0,
      output_tokens: 0,
      thought_tokens: 0,
      total_tokens: 0,
      estimated_nano_usd: 0,
    }
    await screen.findByRole('heading', { name: 'Nessun tentativo registrato in questo mese.' })
    expect(screen.getByRole('region', { name: 'Riepilogo mensile' })).toHaveTextContent('0,003250')
    expect(screen.getByText(/I tentativi precedenti già eliminati/)).toBeInTheDocument()
  })
  it('discards late responses after changing month', async () => {
    const { fetchMock } = setup()
    await screen.findByRole('region', { name: 'Riepilogo mensile' })
    const base = fetchMock.getMockImplementation()!
    let complete!: (response: Response) => void
    fetchMock.mockImplementation((input, init) => {
      if (String(input).includes('month=2026-10-01'))
        return new Promise((resolve) => {
          complete = resolve
        })
      return base(input, init)
    })
    fireEvent.change(screen.getByLabelText('Mese (UTC)'), { target: { value: '2026-10' } })
    await waitFor(() => expect(complete).toBeDefined())
    fireEvent.change(screen.getByLabelText('Mese (UTC)'), { target: { value: '2026-09' } })
    await screen.findByRole('region', { name: 'Riepilogo mensile' })
    const old = usageData()
    old.summary.total_tokens = 999999
    await act(async () => complete(new Response(JSON.stringify(old))))
    expect(screen.queryByText('999.999')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Mese (UTC)')).toHaveValue('2026-09')
  })
  it('supports English labels', async () => {
    localStorage.setItem('tnr-language', 'en')
    setup()
    await screen.findByRole('heading', { name: 'Gemini statistics' })
    await screen.findByRole('region', { name: 'Monthly summary' })
    expect(screen.getByLabelText('Month (UTC)')).toBeInTheDocument()
  })
})
