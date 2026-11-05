import { useEffect, useRef } from 'react'

// Reveal an opened panel without forcing a software keyboard on small screens.
export function usePanelFocus() {
  const ref = useRef<HTMLElement>(null)
  useEffect(() => {
    const panel = ref.current
    const previous = document.activeElement as HTMLElement | null
    const desktop = window.matchMedia?.('(min-width: 721px) and (pointer: fine)').matches
    const target = desktop ? panel?.querySelector<HTMLElement>('input') : null
    const focusTarget = target ?? panel
    focusTarget?.focus()
    return () => {
      // Do not steal focus when the user already moved to another action or view.
      if (
        previous?.isConnected &&
        (panel?.contains(document.activeElement) || document.activeElement === document.body)
      ) {
        previous.focus({ preventScroll: true })
      }
    }
  }, [])
  return ref
}
