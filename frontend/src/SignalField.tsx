import { useEffect, useRef } from 'react'
import logo from '../../docs/assets/tech-news-radar-logo.svg'
import { useLanguage } from './language-context'
import { advanceSignalOrbit, createSignalLayout, type SignalOrbit } from './signal-orbits'

type Signal = SignalOrbit & {
  element: HTMLSpanElement
  x: number
  y: number
  velocityX: number
  velocityY: number
}

const symbols = ['“', '”', '«', '»', '…', '↗', '→', '·', '○', '{', '}', '[', ']', '/', '·']

export function SignalField() {
  const { t } = useLanguage()
  const fieldRef = useRef<HTMLButtonElement>(null)
  const symbolsRef = useRef<HTMLSpanElement>(null)
  const logoRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    const field = fieldRef.current!
    const layer = symbolsRef.current!
    const image = logoRef.current!
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    const finePointer = window.matchMedia?.('(hover: hover) and (pointer: fine)')
    let signals: Signal[] = []
    let width = 0
    let height = 0
    let logoWidth = 0
    let logoHeight = 0
    let frame = 0
    let lastTime: number | null = null
    let visible = typeof IntersectionObserver === 'undefined'
    let innerRadiusX = 0
    let innerRadiusY = 0
    let pointer: { x: number; y: number } | null = null
    let pulse: { x: number; y: number; time: number } | null = null

    function paint(signal: Signal) {
      const inset = width <= 440 ? 14 : 20
      let x = Math.max(inset, Math.min(width - inset, signal.baseX + signal.x))
      let y = Math.max(inset, Math.min(height - inset, signal.baseY + signal.y))
      const dx = x - width / 2
      const dy = y - height / 2
      const boundary = ((dx / innerRadiusX) ** 4 + (dy / innerRadiusY) ** 4) ** 0.25
      // Constrain only the wave displacement; the orbit itself already clears the logo.
      if (boundary < 1) {
        x = width / 2 + (boundary > 0.001 ? dx / boundary : innerRadiusX)
        y = height / 2 + (boundary > 0.001 ? dy / boundary : 0)
      }
      signal.element.style.transform = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) translate(-50%, -50%)`
    }

    function settle() {
      cancelAnimationFrame(frame)
      frame = 0
      lastTime = null
      pointer = null
      pulse = null
      field.dataset.logoActive = 'false'
      for (const signal of signals) {
        signal.x = signal.y = signal.velocityX = signal.velocityY = 0
        paint(signal)
      }
    }

    function build() {
      const bounds = field.getBoundingClientRect()
      if (!bounds.width || !bounds.height || !image.offsetHeight) return
      if (
        Math.abs(bounds.width - width) < 0.5 &&
        Math.abs(bounds.height - height) < 0.5 &&
        logoWidth === image.offsetWidth &&
        logoHeight === image.offsetHeight &&
        signals.length
      )
        return
      settle()
      width = bounds.width
      height = bounds.height
      logoWidth = image.offsetWidth
      logoHeight = image.offsetHeight
      signals = []
      const layout = createSignalLayout(width, height, logoWidth, logoHeight)
      innerRadiusX = layout.innerRadiusX
      innerRadiusY = layout.innerRadiusY
      const fragment = document.createDocumentFragment()
      for (const orbit of layout.orbits) {
        const { index, ring, opacity } = orbit
        const element = document.createElement('span')
        element.className = 'signal-field-glyph'
        element.textContent = symbols[(index * 7 + ring * 5) % symbols.length]
        element.dataset.accent = String(index % 5 === 0 || index % 11 === 0)
        element.style.opacity = String(opacity)
        const signal = { ...orbit, element, x: 0, y: 0, velocityX: 0, velocityY: 0 }
        signals.push(signal)
        fragment.append(element)
        paint(signal)
      }
      layer.replaceChildren(fragment)
      start()
    }

    function animate(now: number) {
      frame = 0
      if (reducedMotion?.matches || !visible || document.hidden) return
      const elapsed = lastTime === null ? 0 : Math.min(1000 / 30, now - lastTime)
      const delta = elapsed / (1000 / 60)
      lastTime = now
      if (pulse && now - pulse.time > 1050) pulse = null
      for (const signal of signals) {
        advanceSignalOrbit(signal, elapsed, width, height)
        let targetX = 0
        let targetY = 0
        if (pointer) {
          const dx = signal.baseX - pointer.x
          const dy = signal.baseY - pointer.y
          const distance = Math.hypot(dx, dy)
          if (distance < 110) {
            const force = (1 - distance / 110) ** 1.5 * 44
            targetX += (dx / (distance || 1)) * force
            targetY += (dy / (distance || 1)) * force
          }
        }
        if (pulse) {
          const dx = signal.baseX - pulse.x
          const dy = signal.baseY - pulse.y
          const distance = Math.hypot(dx, dy)
          const age = (now - pulse.time) / 1000
          const force =
            Math.exp(-(((distance - age * 400) / 46) ** 2)) * Math.max(0, 1 - age / 1.05) * 36
          targetX += (dx / (distance || 1)) * force
          targetY += (dy / (distance || 1)) * force
        }
        signal.velocityX = (signal.velocityX + (targetX - signal.x) * 0.075 * delta) * 0.72 ** delta
        signal.velocityY = (signal.velocityY + (targetY - signal.y) * 0.075 * delta) * 0.72 ** delta
        signal.x += signal.velocityX * delta
        signal.y += signal.velocityY * delta
        paint(signal)
      }
      frame = requestAnimationFrame(animate)
    }

    function start() {
      if (!frame && signals.length && !reducedMotion?.matches && visible && !document.hidden) {
        lastTime = null
        frame = requestAnimationFrame(animate)
      }
    }

    function move(event: PointerEvent) {
      if (
        reducedMotion?.matches ||
        !finePointer?.matches ||
        width <= 440 ||
        event.pointerType !== 'mouse'
      )
        return
      const bounds = field.getBoundingClientRect()
      pointer = { x: event.clientX - bounds.left, y: event.clientY - bounds.top }
      field.dataset.logoActive = String(
        Math.abs(pointer.x - width / 2) < logoWidth / 2 &&
          Math.abs(pointer.y - height / 2) < logoHeight / 2,
      )
      start()
    }

    function leave() {
      pointer = null
      field.dataset.logoActive = 'false'
      start()
    }

    function activate(event: MouseEvent) {
      if (reducedMotion?.matches) return
      const bounds = field.getBoundingClientRect()
      pointer = null
      pulse = {
        x: event.detail === 0 ? width / 2 : event.clientX - bounds.left,
        y: event.detail === 0 ? height / 2 : event.clientY - bounds.top,
        time: performance.now(),
      }
      start()
    }

    function visibilityChanged() {
      if (document.hidden || !visible || reducedMotion?.matches) settle()
      else start()
    }

    function pointerChanged() {
      leave()
    }

    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(build)
    resizeObserver?.observe(field)
    resizeObserver?.observe(image)
    const intersectionObserver =
      typeof IntersectionObserver === 'undefined'
        ? null
        : new IntersectionObserver(([entry]) => {
            visible = entry.isIntersecting
            visibilityChanged()
          })
    intersectionObserver?.observe(field)
    image.addEventListener('load', build)
    window.addEventListener('resize', build)
    field.addEventListener('pointermove', move)
    field.addEventListener('pointerleave', leave)
    field.addEventListener('pointercancel', leave)
    field.addEventListener('click', activate)
    reducedMotion?.addEventListener('change', visibilityChanged)
    finePointer?.addEventListener('change', pointerChanged)
    document.addEventListener('visibilitychange', visibilityChanged)
    build()

    return () => {
      settle()
      resizeObserver?.disconnect()
      intersectionObserver?.disconnect()
      image.removeEventListener('load', build)
      window.removeEventListener('resize', build)
      field.removeEventListener('pointermove', move)
      field.removeEventListener('pointerleave', leave)
      field.removeEventListener('pointercancel', leave)
      field.removeEventListener('click', activate)
      reducedMotion?.removeEventListener('change', visibilityChanged)
      finePointer?.removeEventListener('change', pointerChanged)
      document.removeEventListener('visibilitychange', visibilityChanged)
      layer.replaceChildren()
    }
  }, [])

  return (
    <button
      ref={fieldRef}
      className="signal-field"
      type="button"
      aria-label={t(
        'Tech News Radar: interactive signals. Move the pointer or tap; press Enter or Space to create a wave.',
      )}
    >
      <span ref={symbolsRef} className="signal-field-symbols" aria-hidden="true" />
      <img ref={logoRef} className="access-logo" src={logo} alt="Tech News Radar" />
    </button>
  )
}
