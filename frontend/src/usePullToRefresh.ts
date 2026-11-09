import { useEffect, useRef, useState } from 'react'

const THRESHOLD = 90

export function usePullToRefresh(refresh: () => void, disabled: boolean) {
  const surface = useRef<HTMLDivElement>(null)
  const [pull, setPull] = useState(0)
  useEffect(() => {
    const element = surface.current
    if (!element) return
    let start: { x: number; y: number } | null = null
    let distance = 0
    function reset() {
      start = null
      distance = 0
      setPull(0)
    }
    function begin(event: TouchEvent) {
      reset()
      const touch = event.touches[0]
      if (
        disabled ||
        event.touches.length !== 1 ||
        window.scrollY > 0 ||
        document.documentElement.scrollTop > 0 ||
        !touch ||
        touch.clientX < 24 ||
        touch.clientX > window.innerWidth - 24 ||
        (event.target instanceof Element &&
          event.target.closest('a, button, input, select, textarea, [role="slider"]'))
      )
        return
      start = { x: touch.clientX, y: touch.clientY }
    }
    function move(event: TouchEvent) {
      if (!start) return
      if (event.touches.length !== 1 || window.scrollY > 0) return reset()
      const touch = event.touches[0]
      const dx = Math.abs(touch.clientX - start.x)
      const dy = touch.clientY - start.y
      if (dy < 0 || (dx > 10 && dx >= dy)) return reset()
      if (dy < 10) return
      if (!event.cancelable) return reset()
      // A non-passive listener prevents native refresh only for this intentional gesture.
      event.preventDefault()
      distance = Math.min(dy, 150)
      setPull(distance)
    }
    function end() {
      const ready = distance >= THRESHOLD
      reset()
      if (ready && !disabled) refresh()
    }
    document.documentElement.classList.add('news-pull-refresh')
    element.addEventListener('touchstart', begin, { passive: true })
    element.addEventListener('touchmove', move, { passive: false })
    element.addEventListener('touchend', end)
    element.addEventListener('touchcancel', reset)
    return () => {
      document.documentElement.classList.remove('news-pull-refresh')
      element.removeEventListener('touchstart', begin)
      element.removeEventListener('touchmove', move)
      element.removeEventListener('touchend', end)
      element.removeEventListener('touchcancel', reset)
    }
  }, [refresh, disabled])
  return { surface, pulling: pull > 0, ready: pull >= THRESHOLD }
}
