import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { AccountMenu } from '../AccountMenu'
import { release, releaseStorageKey } from '../release'

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})
const user = { id: 'reader', display_name: 'Alice', role: 'reader' as const }

it('closes temporarily and appears again on opening the app', async () => {
  const view = render(<AccountMenu user={user} />)
  await userEvent.click(screen.getByRole('button', { name: 'Chiudi novità' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  view.unmount()
  render(<AccountMenu user={user} />)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

it('remembers the selected version for one user and supports reopening from the menu', async () => {
  const view = render(<AccountMenu user={user} />)
  await userEvent.click(screen.getByRole('checkbox'))
  fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
  expect(localStorage.getItem(releaseStorageKey(user.id))).toBe(release.version)
  view.unmount()
  render(<AccountMenu user={user} />)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Menu account e tema' }))
  await userEvent.click(screen.getByRole('button', { name: /Versione 0.2.0/ }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

it('shows a new release and does not share the preference between users', () => {
  localStorage.setItem(releaseStorageKey(user.id), '0.1.0')
  const view = render(<AccountMenu user={user} />)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  view.unmount()
  localStorage.setItem(releaseStorageKey(user.id), release.version)
  render(<AccountMenu user={{ ...user, id: 'other' }} />)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})
