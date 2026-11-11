import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../src/App'
import { mockServer } from './server'

function open() {
  history.replaceState(null, '', '#briefs')
  return render(<App />)
}
const saved = {
  id: 'brief-1',
  category_name: 'Intelligenza artificiale',
  generated_at: '2026-11-09T11:00:00Z',
  window_start: '2026-11-08T11:00:00Z',
  window_end: '2026-11-09T11:00:00Z',
  summary: 'Una sintesi condivisa in italiano.',
  articles: [
    {
      id: 1,
      title: 'Un articolo verificabile',
      url: 'https://example.org/story',
      source: 'Example News',
      date: '2026-11-09T10:00:00Z',
      date_is_fetched: false,
      removed: true,
    },
  ],
}

describe('shared hourly digest', () => {
  it.each([
    {
      language: 'it',
      help: 'Come funziona la rassegna AI?',
      explanation:
        'La rassegna usa fino a 12 articoli delle ultime 24 ore. Le edizioni restano disponibili per 7 giorni.',
      refresh: 'Aggiorna elenco',
    },
    {
      language: 'en',
      help: 'How does the AI digest work?',
      explanation:
        'The digest uses up to 12 articles from the last 24 hours. Editions are saved for 7 days.',
      refresh: 'Refresh list',
    },
  ])('keeps help collapsed and refresh read-only in $language', async (copy) => {
    const { state, calls } = mockServer()
    state.brief.code = 'cached'
    state.brief.retry_at = '2026-11-10T04:00:00Z'
    state.brief.briefs = [structuredClone(saved)]
    open()
    await screen.findByText(saved.summary)
    if (copy.language === 'en') {
      await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
      await userEvent.selectOptions(screen.getByLabelText('Lingua'), 'en')
      await userEvent.keyboard('{Escape}')
    }
    const help = screen.getByText(copy.help)
    const explanation = screen.getByText(copy.explanation)
    expect(explanation).not.toBeVisible()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    const initialCalls = calls.length
    await userEvent.click(help)
    expect(explanation).toBeVisible()
    await userEvent.click(help)
    expect(explanation).not.toBeVisible()
    expect(calls).toHaveLength(initialCalls)
    const reads = calls.filter((c) => c.path === '/api/briefs/digest').length
    await userEvent.click(screen.getByRole('button', { name: copy.refresh }))
    await waitFor(() =>
      expect(calls.filter((c) => c.path === '/api/briefs/digest')).toHaveLength(reads + 1),
    )
    expect(calls.filter((c) => c.method !== 'GET')).toHaveLength(0)
    expect(screen.getByText(saved.summary)).toBeVisible()
  })

  it('explains pending operator activation in both languages without generating', async () => {
    const { state, calls } = mockServer()
    state.brief.code = 'activation_required'
    state.brief.briefs = [structuredClone(saved)]
    open()
    await screen.findByText(saved.summary)
    expect(screen.getByRole('status')).toHaveTextContent(
      'L’attivazione di Gemini non è configurata dal gestore.',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await userEvent.selectOptions(screen.getByLabelText('Lingua'), 'en')
    expect(screen.getByRole('status')).toHaveTextContent(
      'Gemini activation is not configured by the operator.',
    )
    expect(screen.getByText(saved.summary)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('keeps saved editions visible when the monthly USD budget is exhausted in both languages', async () => {
    const { state, calls } = mockServer()
    state.brief.code = 'monthly_budget'
    state.brief.briefs = [structuredClone(saved)]
    open()
    await screen.findByText(saved.summary)
    expect(screen.getByRole('status')).toHaveTextContent(
      'Budget mensile locale di 2,00 USD esaurito.',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await userEvent.selectOptions(screen.getByLabelText('Lingua'), 'en')
    expect(screen.getByRole('status')).toHaveTextContent(
      'The local monthly budget of USD 2.00 is exhausted.',
    )
    expect(screen.getByText(saved.summary)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('reads shared cache on open, refresh and return without generation', async () => {
    const { state, calls } = mockServer()
    state.user.role = 'reader'
    state.subscriptions = []
    state.brief.briefs = [structuredClone(saved)]
    const view = open()
    await screen.findByText(saved.summary)
    expect(screen.getByRole('link', { name: 'Rassegna AI' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: 'Un articolo verificabile' })).toHaveAttribute(
      'href',
      'https://example.org/story',
    )
    expect(screen.getByText(/Rimosso dal lettore/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Categoria')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Genera sintesi' })).not.toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Aggiorna elenco' })).toBeEnabled(),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Aggiorna elenco' }))
    view.unmount()
    open()
    await screen.findByText(saved.summary)
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
    expect(calls.filter((c) => c.path === '/api/briefs/digest').length).toBeGreaterThan(1)
  })

  it('keeps cache at the daily limit and translates without generating', async () => {
    const { state, calls } = mockServer()
    state.brief.briefs = [structuredClone(saved)]
    state.brief.code = 'daily_limit'
    open()
    await screen.findByText(saved.summary)
    const exact =
      'Limite giornaliero raggiunto. La generazione sarà nuovamente disponibile al ripristino della quota'
    expect(screen.getByRole('status')).toHaveTextContent(exact)
    await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
    await userEvent.selectOptions(screen.getByLabelText('Lingua'), 'en')
    expect(screen.getByRole('heading', { name: 'Last 24 hours digest' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('The daily limit has been reached.')
    expect(screen.getByText(saved.summary)).toHaveAttribute('lang', 'it')
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it.each([
    'disabled',
    'monthly_budget',
    'activation_required',
    'input_limit',
    'empty',
    'insufficient_material',
    'model_unavailable',
    'temporary_limit',
    'uncertain',
    'busy',
    'safety_stop',
    'unchanged',
    'edition_attempted',
  ])('shows %s without exposing generation controls', async (code) => {
    const { state, calls } = mockServer()
    state.brief.code = code
    state.brief.can_generate = true
    open()
    await screen.findByText('Non ci sono ancora rassegne salvate.')
    expect(screen.getByRole('status')).not.toBeEmptyDOMElement()
    expect(screen.queryByRole('button', { name: 'Genera sintesi' })).not.toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('renders untrusted text and rejects unsafe links', async () => {
    const { state } = mockServer()
    state.brief.briefs = [
      {
        ...saved,
        summary: '<img src=x onerror=alert(1)>',
        articles: [
          { ...saved.articles[0], url: 'javascript:alert(1)', title: '<script>bad()</script>' },
        ],
      },
    ]
    open()
    await screen.findByText('<img src=x onerror=alert(1)>')
    expect(screen.queryByRole('link', { name: '<script>bad()</script>' })).not.toBeInTheDocument()
    expect(document.querySelector('.brief-summary img')).toBeNull()
  })

  it('keeps the latest success visible after a failed scheduled attempt', async () => {
    const { state } = mockServer()
    state.brief.code = 'edition_attempted'
    state.brief.last_error_code = 'uncertain'
    state.brief.briefs = [structuredClone(saved)]
    open()
    await screen.findByText(saved.summary)
    expect(screen.getByText(/Il tentativo di questa ora è concluso/)).toBeInTheDocument()
    expect(screen.getByText(/L’esito del tentativo precedente è incerto/)).toBeInTheDocument()
  })
})
