import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AccountMenu } from '../src/AccountMenu'
import { ThemeProvider } from '../src/Theme'

function open() {
  render(
    <ThemeProvider>
      <AccountMenu user={{ id: 'reader', display_name: 'Alice', role: 'reader' }} />
      <button>Outside</button>
    </ThemeProvider>,
  )
  return screen.getByRole('button', { name: 'Menu account e tema' })
}

describe('account disclosure', () => {
  it('supports keyboard access and returns focus to the trigger on Escape', async () => {
    const trigger = open()
    expect(screen.queryByText('Alice')).not.toBeInTheDocument()
    await userEvent.tab()
    expect(trigger).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Alice')).toBeVisible()
    expect(screen.getByText('Lettore')).toBeVisible()
    await userEvent.tab()
    expect(screen.getByRole('combobox', { name: 'Tema' })).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    expect(trigger).toHaveFocus()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('region', { name: 'Account e tema' })).not.toBeInTheDocument()
  })

  it('closes on an outside click or when keyboard focus leaves, without trapping focus', async () => {
    const trigger = open()
    await userEvent.click(trigger)
    await userEvent.click(screen.getByRole('button', { name: 'Outside' }))
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: 'Outside' })).toHaveFocus()
    await userEvent.click(trigger)
    await userEvent.tab()
    await userEvent.tab()
    expect(screen.getByRole('combobox', { name: 'Lingua' })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('link', { name: 'Privacy e dati personali' })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('button', { name: /Versione/ })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Outside' })).toHaveFocus()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })
})
