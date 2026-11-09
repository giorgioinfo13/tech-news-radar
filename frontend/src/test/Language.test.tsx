import { readFileSync } from 'node:fs'
import { StrictMode } from 'react'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { formatDate } from '../api'
import { mockServer, article } from './server'

async function choose(language: 'it' | 'en') {
  const trigger = screen.getByRole('button', {
    name: /Menu account e tema|Account and appearance menu/,
  })
  if (trigger.getAttribute('aria-expanded') !== 'true') await userEvent.click(trigger)
  await userEvent.selectOptions(screen.getByRole('combobox', { name: /Lingua|Language/ }), language)
  await userEvent.keyboard('{Escape}')
}

afterEach(() => vi.restoreAllMocks())

describe('interface language', () => {
  it('defaults to Italian and changes labels and dates without resetting filters or refetching data', async () => {
    const { calls } = mockServer()
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US')
    render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
    await screen.findByRole('heading', { name: 'Notizie' })
    await userEvent.type(screen.getByLabelText('Cerca nelle notizie'), 'Draft search')
    await userEvent.click(screen.getByRole('button', { name: 'Da leggere' }))
    await screen.findByRole('link', { name: /Una nuova idea/ })
    const count = calls.length
    await choose('en')
    expect(screen.getByRole('heading', { name: 'News' })).toBeInTheDocument()
    expect(document.documentElement).toHaveAttribute('lang', 'en')
    expect(localStorage.getItem('tnr-language')).toBe('en')
    expect(screen.getByLabelText('Search news')).toHaveValue('Draft search')
    expect(screen.getByRole('button', { name: 'Unread' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('link', { name: /Una nuova idea/ })).toBeInTheDocument()
    expect(screen.getByText(formatDate(article.published_at, 'en-GB'))).toBeInTheDocument()
    expect(calls).toHaveLength(count)
    await choose('it')
    expect(screen.getByLabelText('Cerca nelle notizie')).toHaveValue('Draft search')
    expect(document.documentElement).toHaveAttribute('lang', 'it')
    expect(calls).toHaveLength(count)
  })

  it('restores English after remount and synchronizes other tabs or clearing storage', async () => {
    mockServer()
    localStorage.setItem('tnr-language', 'en')
    const first = render(<App />)
    await screen.findByRole('heading', { name: 'News' })
    first.unmount()
    render(<App />)
    await screen.findByRole('heading', { name: 'News' })
    act(() =>
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'tnr-language',
          newValue: 'it',
          storageArea: sessionStorage,
        }),
      ),
    )
    expect(document.documentElement).toHaveAttribute('lang', 'en')
    act(() =>
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'tnr-language',
          newValue: 'it',
          storageArea: localStorage,
        }),
      ),
    )
    expect(screen.getByRole('heading', { name: 'Notizie' })).toBeInTheDocument()
    await choose('en')
    act(() =>
      window.dispatchEvent(
        new StorageEvent('storage', { key: null, newValue: null, storageArea: localStorage }),
      ),
    )
    expect(screen.getByRole('heading', { name: 'Notizie' })).toBeInTheDocument()
  })

  it('uses Italian for unknown saved values and still switches when storage is blocked', async () => {
    mockServer()
    localStorage.setItem('tnr-language', 'fr')
    const view = render(<App />)
    await screen.findByRole('heading', { name: 'Notizie' })
    view.unmount()
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    render(<App />)
    await screen.findByRole('heading', { name: 'Notizie' })
    await choose('en')
    expect(screen.getByRole('heading', { name: 'News' })).toBeInTheDocument()
  })

  it('translates existing API errors without repeating a refresh', async () => {
    const { state, calls } = mockServer()
    state.failRefresh = 502
    history.replaceState(null, '', '/#catalog')
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Aggiorna Example News' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Il refresh non è riuscito.')
    const count = calls.length
    await choose('en')
    expect(screen.getByRole('alert')).toHaveTextContent('The refresh failed.')
    expect(calls).toHaveLength(count)
  })

  it('keeps invitation drafts and translates dynamic success messages when switching language', async () => {
    const { calls } = mockServer()
    history.replaceState(null, '', '/#invitations')
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Nome'), 'Friend')
    await userEvent.type(screen.getByLabelText('Email Google'), 'friend@example.org')
    const count = calls.length
    await choose('en')
    expect(screen.getByLabelText('Name')).toHaveValue('Friend')
    expect(screen.getByLabelText('Google email')).toHaveValue('friend@example.org')
    expect(calls).toHaveLength(count)
    await userEvent.click(screen.getByRole('button', { name: 'Save invitation' }))
    await screen.findByText('friend@example.org')
    expect(screen.getByRole('status')).toHaveTextContent('Invitation saved.')
    await userEvent.click(
      screen.getByRole('button', { name: 'Cancel invitation for friend@example.org' }),
    )
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Invitation for friend@example.org canceled.',
    )
    await choose('it')
    expect(screen.getByRole('status')).toHaveTextContent('Invito per friend@example.org annullato.')
  })

  it('preserves source editor input and translates category confirmation dialogs', async () => {
    mockServer()
    history.replaceState(null, '', '/#catalog')
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Aggiungi fonte' }))
    await userEvent.type(screen.getByLabelText('Nome della fonte'), 'My draft')
    await choose('en')
    expect(screen.getByLabelText('Source name')).toHaveValue('My draft')
    expect(screen.getByRole('button', { name: 'Save source' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: 'Categories' }))
    await userEvent.click(
      await screen.findByRole('button', { name: 'Delete Intelligenza artificiale' }),
    )
    const dialog = screen.getByRole('dialog')
    expect(
      within(dialog).getByRole('heading', { name: 'Delete Intelligenza artificiale?' }),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText(
        'Assigned sources will become uncategorized. Articles and sources will be kept.',
      ),
    ).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  })

  it('translates the reader onboarding and offers the matching public privacy page', async () => {
    const { state } = mockServer()
    state.user.role = 'reader'
    state.subscriptions = []
    render(<App />)
    await screen.findByRole('heading', { name: 'Scegli da dove iniziare' })
    await choose('en')
    expect(screen.getByRole('button', { name: 'Follow 1 source and continue' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Invitations' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Account and appearance menu' }))
    const menu = screen.getByRole('region', { name: 'Account and appearance' })
    expect(within(menu).getByText('Reader')).toBeInTheDocument()
    expect(within(menu).getByRole('link', { name: 'Privacy and personal data' })).toHaveAttribute(
      'href',
      '/privacy.en.html',
    )
    const privacy = new DOMParser().parseFromString(
      readFileSync('public/privacy.en.html', 'utf8'),
      'text/html',
    )
    expect(privacy.documentElement.lang).toBe('en')
    expect(privacy.body.textContent).toContain('language preferences')
    expect(privacy.querySelector('a[href="/privacy.html"]')).not.toBeNull()
  })
})
