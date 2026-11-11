import { useEffect, useRef } from 'react'
import logo from '../../docs/assets/tech-news-radar-logo.svg'
import { useLanguage } from './language-context'

type Signal = {
  element: HTMLSpanElement
  baseX: number
  baseY: number
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
    let lastTime = 0
    let visible = true
    let pointer: { x: number; y: number } | null = null
    let pulse: { x: number; y: number; time: number } | null = null

    function paint(signal: Signal) {
      let x = signal.baseX + signal.x
      let y = signal.baseY + signal.y
      const dx = x - width / 2
      const dy = y - height / 2
      const radiusX = logoWidth / 2 + 24
      const radiusY = logoHeight / 2 + 28
      // Keep moving symbols outside the central logo, including its enlarged state.
      const boundary = ((Math.abs(dx) / radiusX) ** 4 + (Math.abs(dy) / radiusY) ** 4) ** 0.25
      if (boundary < 1) {
        x = width / 2 + (boundary > 0.001 ? dx / boundary : radiusX)
        y = height / 2 + (boundary > 0.001 ? dy / boundary : 0)
      }
      signal.element.style.transform = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) translate(-50%, -50%)`
    }

    function settle() {
      cancelAnimationFrame(frame)
      frame = 0
      lastTime = 0
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
      const columns = width < 400 ? 11 : 23
      const rows = 11
      const fragment = document.createDocumentFragment()
      for (let row = 0; row < rows; row++) {
        for (let column = 0; column < columns; column++) {
          const nx = (column - (columns - 1) / 2) / ((columns - 1) / 2)
          const ny = (row - (rows - 1) / 2) / ((rows - 1) / 2)
          if (nx * nx + ny * ny > 1.3) continue
          const baseX =
            20 + (column * (width - 40)) / (columns - 1) + Math.sin(row * 1.8 + column * 0.7) * 3
          const baseY =
            23 + (row * (height - 46)) / (rows - 1) + Math.sin(column * 0.55 + row * 0.8) * 7
          if (
            (Math.abs(baseX - width / 2) / (logoWidth / 2 + 32)) ** 4 +
              (Math.abs(baseY - height / 2) / (logoHeight / 2 + 36)) ** 4 <
            1
          )
            continue
          const index = row * columns + column
          const element = document.createElement('span')
          element.className = 'signal-field-glyph'
          element.textContent = symbols[(index * 7 + row * 5) % symbols.length]
          element.dataset.accent = String(index % 5 === 0 || index % 11 === 0)
          element.style.opacity = String(0.38 + 0.5 * (1 - Math.min(1, (nx * nx + ny * ny) / 2)))
          const signal = { element, baseX, baseY, x: 0, y: 0, velocityX: 0, velocityY: 0 }
          signals.push(signal)
          fragment.append(element)
          paint(signal)
        }
      }
      layer.replaceChildren(fragment)
    }

    function animate(now: number) {
      frame = 0
      if (reducedMotion?.matches || !visible || document.hidden) return
      const delta = Math.min(2, lastTime ? (now - lastTime) / (1000 / 60) : 1)
      lastTime = now
      if (pulse && now - pulse.time > 1050) pulse = null
      let moving = false
      for (const signal of signals) {
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
        if (
          Math.abs(targetX - signal.x) +
            Math.abs(targetY - signal.y) +
            Math.abs(signal.velocityX) +
            Math.abs(signal.velocityY) >
          0.03
        )
          moving = true
        paint(signal)
      }
      // No idle animation: only schedule frames while responding to an interaction.
      if (moving || pulse) frame = requestAnimationFrame(animate)
      else lastTime = 0
    }

    function start() {
      if (!frame && signals.length && !reducedMotion?.matches && visible && !document.hidden) {
        lastTime = 0
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
      if (document.hidden) settle()
    }

    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(build)
    resizeObserver?.observe(field)
    resizeObserver?.observe(image)
    const intersectionObserver =
      typeof IntersectionObserver === 'undefined'
        ? null
        : new IntersectionObserver(([entry]) => {
            visible = entry.isIntersecting
            if (!visible) settle()
          })
    intersectionObserver?.observe(field)
    image.addEventListener('load', build)
    window.addEventListener('resize', build)
    field.addEventListener('pointermove', move)
    field.addEventListener('pointerleave', leave)
    field.addEventListener('pointercancel', leave)
    field.addEventListener('click', activate)
    reducedMotion?.addEventListener('change', settle)
    finePointer?.addEventListener('change', settle)
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
      reducedMotion?.removeEventListener('change', settle)
      finePointer?.removeEventListener('change', settle)
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
