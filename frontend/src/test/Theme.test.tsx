import { readFileSync } from 'node:fs'
import { StrictMode } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { ThemeProvider, ThemeSelector } from '../Theme'
import { mockServer } from './server'

const bootstrap = readFileSync('public/theme.js', 'utf8')
let media: MediaQueryList
let listeners: Set<() => void>
function systemDark(value: boolean) {
  Object.defineProperty(media, 'matches', { value, configurable: true })
  act(() => listeners.forEach((listener) => listener()))
}
function openSelector() {
  return render(
    <StrictMode>
      <ThemeProvider>
        <ThemeSelector />
      </ThemeProvider>
    </StrictMode>,
  )
}
beforeEach(() => {
  localStorage.clear()
  listeners = new Set()
  media = {
    matches: false,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  } as unknown as MediaQueryList
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => media),
  )
  const meta = document.createElement('meta')
  meta.name = 'theme-color'
  document.head.append(meta)
})
afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  delete document.documentElement.dataset.theme
  document.querySelector('meta[name="theme-color"]')?.remove()
})

describe('appearance preference', () => {
  it('restores the saved theme before React renders and keeps the selector consistent', () => {
    localStorage.setItem('tnr-theme', 'dark')
    new Function(bootstrap)()
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute('content', '#141e2b')
    openSelector()
    expect(screen.getByLabelText('Tema')).toHaveValue('dark')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })
  it('follows system changes and treats an invalid saved value as system', () => {
    localStorage.setItem('tnr-theme', 'unexpected')
    systemDark(true)
    new Function(bootstrap)()
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    const view = openSelector()
    expect(screen.getByLabelText('Tema')).toHaveValue('system')
    systemDark(false)
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute('content', '#f4f6f8')
    view.unmount()
    expect(listeners.size).toBe(0)
  })
  it('persists choices and ignores system changes until system is selected again', async () => {
    openSelector()
    const selector = screen.getByLabelText('Tema')
    await userEvent.selectOptions(selector, 'dark')
    expect(localStorage.getItem('tnr-theme')).toBe('dark')
    systemDark(false)
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    await userEvent.selectOptions(selector, 'light')
    systemDark(true)
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    await userEvent.selectOptions(selector, 'system')
    expect(localStorage.getItem('tnr-theme')).toBe('system')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })
  it('synchronizes other tabs and storage clearing, ignoring unrelated or session storage', () => {
    openSelector()
    const update = (key: string | null, newValue: string | null, storageArea = localStorage) => {
      act(() => window.dispatchEvent(new StorageEvent('storage', { key, newValue, storageArea })))
    }
    update('tnr-theme', 'dark')
    expect(screen.getByLabelText('Tema')).toHaveValue('dark')
    update('unrelated', 'light')
    update('tnr-theme', 'light', sessionStorage)
    expect(screen.getByLabelText('Tema')).toHaveValue('dark')
    update(null, null)
    expect(screen.getByLabelText('Tema')).toHaveValue('system')
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })
  it('keeps the interface usable when storage access is blocked', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    systemDark(true)
    new Function(bootstrap)()
    openSelector()
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    await userEvent.selectOptions(screen.getByLabelText('Tema'), 'light')
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })
  it('changes appearance without resetting filters or fetching application data again', async () => {
    const { calls } = mockServer()
    render(<App />)
    await screen.findByRole('link', { name: /Una nuova idea/ })
    await userEvent.type(screen.getByLabelText('Cerca nelle notizie'), 'My draft')
    const count = calls.length
    await userEvent.selectOptions(screen.getByLabelText('Tema'), 'dark')
    expect(screen.getByLabelText('Cerca nelle notizie')).toHaveValue('My draft')
    expect(calls).toHaveLength(count)
    act(() => {
      location.hash = '#sources'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Le mie fonti' })).toBeInTheDocument(),
    )
    expect(screen.getByLabelText('Tema')).toHaveValue('dark')
  })
  it('offers the control before login without requesting application data', async () => {
    const { calls } = mockServer()
    vi.stubEnv('VITE_LOCAL_MODE', 'false')
    render(<App />)
    await screen.findByRole('heading', { name: 'Il radar si sta preparando' })
    await userEvent.selectOptions(screen.getByLabelText('Tema'), 'dark')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(calls).toHaveLength(0)
  })
})
