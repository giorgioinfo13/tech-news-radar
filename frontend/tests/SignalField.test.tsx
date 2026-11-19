import { StrictMode } from 'react'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SignalField } from '../src/SignalField'

let frames: Map<number, FrameRequestCallback>
let motion: MediaQueryList
let motionListeners: Set<() => void>
let fieldWidth: number
let fieldHeight: number
let logoWidth: number
let logoHeight: number

beforeEach(() => {
  frames = new Map()
  motionListeners = new Set()
  fieldWidth = 680
  fieldHeight = 330
  logoWidth = 380
  logoHeight = (logoWidth * 280) / 612
  let frameId = 0
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.set(++frameId, callback)
    return frameId
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
  vi.spyOn(performance, 'now').mockReturnValue(0)
  motion = {
    matches: false,
    addEventListener: (_: string, callback: () => void) => motionListeners.add(callback),
    removeEventListener: (_: string, callback: () => void) => motionListeners.delete(callback),
  } as unknown as MediaQueryList
  vi.stubGlobal('matchMedia', (query: string) =>
    query.includes('reduced-motion')
      ? motion
      : { matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() },
  )
  vi.stubGlobal(
    'PointerEvent',
    class extends MouseEvent {
      pointerType: string
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init)
        this.pointerType = init.pointerType ?? 'mouse'
      }
    },
  )
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
    () => ({ left: 0, top: 0, width: fieldWidth, height: fieldHeight }) as DOMRect,
  )
  vi.spyOn(HTMLImageElement.prototype, 'offsetWidth', 'get').mockImplementation(() => logoWidth)
  vi.spyOn(HTMLImageElement.prototype, 'offsetHeight', 'get').mockImplementation(() => logoHeight)
})

function runFrame(time: number) {
  const pending = [...frames.values()]
  frames.clear()
  pending.forEach((callback) => callback(time))
}

function nextFrame(time: number) {
  act(() => runFrame(time))
}

function positions(field: HTMLElement) {
  return Array.from(
    field.querySelectorAll<HTMLElement>('.signal-field-glyph'),
    (signal) => signal.style.transform,
  )
}

function open() {
  const view = render(
    <StrictMode>
      <SignalField />
    </StrictMode>,
  )
  const field = within(view.container).getByRole('button', {
    name: /Tech News Radar: segnali interattivi/,
  })
  return { ...view, field }
}

function trackPath(field: HTMLElement) {
  const scale = fieldWidth <= 440 ? 1 : 1.045
  const glyphs = Array.from(field.querySelectorAll<HTMLElement>('.signal-field-glyph'))
  expect(glyphs.length).toBeGreaterThanOrEqual(20)
  const violations: { time: number; index: number; x: number; y: number }[] = []
  const previousAngles: number[] = []
  const angularTravel = glyphs.map(() => 0)
  const sample = (time: number) => {
    glyphs.forEach((glyph, index) => {
      const [, rawX, rawY] = glyph.style.transform.match(/translate\(([\d.-]+)px, ([\d.-]+)px\)/)!
      const x = Number(rawX)
      const y = Number(rawY)
      const outsideLogo =
        Math.abs(x - fieldWidth / 2) >= (logoWidth * scale) / 2 + 8 ||
        Math.abs(y - fieldHeight / 2) >= (logoHeight * scale) / 2 + 8
      if (
        !Number.isFinite(x) ||
        !Number.isFinite(y) ||
        x < 12 ||
        x > fieldWidth - 12 ||
        y < 12 ||
        y > fieldHeight - 12 ||
        !outsideLogo
      )
        violations.push({ time, index, x, y })

      // Measure the rendered path, independently of the animation's orbit formula.
      const angle = Math.atan2(y - fieldHeight / 2, x - fieldWidth / 2)
      if (previousAngles[index] !== undefined) {
        const change = angle - previousAngles[index]
        angularTravel[index] += Math.atan2(Math.sin(change), Math.cos(change))
      }
      previousAngles[index] = angle
    })
  }
  return { sample, violations, angularTravel }
}

describe('interactive welcome signals', () => {
  it.each([
    { width: 265, height: 310, imageWidth: 170 },
    { width: 335, height: 310, imageWidth: 214 },
    { width: 390, height: 310, imageWidth: 250 },
    { width: 440, height: 310, imageWidth: 280 },
    { width: 441, height: 330, imageWidth: 300 },
    { width: 680, height: 330, imageWidth: 380 },
    { width: 980, height: 440, imageWidth: 490 },
    { width: 1200, height: 440, imageWidth: 544 },
    { width: 1120, height: 380, imageWidth: 448 },
  ])(
    'keeps rotating symbols clear of the logo and edges at $width × $height',
    ({ width, height, imageWidth }) => {
      fieldWidth = width
      fieldHeight = height
      logoWidth = imageWidth
      logoHeight = (logoWidth * 280) / 612
      const { field } = open()
      const path = trackPath(field)
      // Cover the entire edge-triggered wave at every size, without repeating a
      // minute of DOM animation for each breakpoint. Full turns are checked below.
      act(() => {
        for (let step = 0; step <= 120; step++) {
          const time = (step * 100) / 6
          if (step === 30) {
            vi.mocked(performance.now).mockReturnValue(time)
            fireEvent.click(field, { detail: 1, clientX: width - 20, clientY: fieldHeight / 2 })
          }
          runFrame(time)
          path.sample(time)
        }
      })
      expect(path.violations).toEqual([])
      expect(frames.size).toBe(1)
    },
  )

  it.each([
    { layout: 'mobile', width: 335, height: 310, imageWidth: 214 },
    { layout: 'desktop with multiple rings', width: 980, height: 380, imageWidth: 420 },
  ])('completes a full clockwise turn on $layout', ({ width, height, imageWidth, layout }) => {
    fieldWidth = width
    fieldHeight = height
    logoWidth = imageWidth
    logoHeight = (logoWidth * 280) / 612
    const { field } = open()
    const path = trackPath(field)
    path.sample(0)
    // Run the real animation at 30 fps for 60 seconds, including the slowest ring.
    // Batch React work; keep the DOM writes and observe the rendered positions.
    act(() => {
      for (let step = 0; step <= 1800; step++) {
        const time = (step * 100) / 3
        runFrame(time)
        if (step % 30 === 0) path.sample(time)
      }
    })
    expect(path.violations).toEqual([])
    // A static field would pass clearance checks, but must fail this assertion.
    expect(Math.min(...path.angularTravel)).toBeGreaterThanOrEqual(2 * Math.PI - 0.01)
    if (layout === 'desktop with multiple rings') {
      expect(Math.max(...path.angularTravel) - Math.min(...path.angularTravel)).toBeGreaterThan(0.5)
    }
    expect(frames.size).toBe(1)
  })

  it('rebuilds the orbits when resizing between desktop and mobile without duplicating the loop', () => {
    const { field } = open()
    const desktop = positions(field)
    fieldWidth = 350
    logoWidth = fieldWidth * 0.64
    logoHeight = (logoWidth * 280) / 612
    fireEvent(window, new Event('resize'))
    expect(positions(field).length).toBeGreaterThan(0)
    expect(positions(field)).not.toEqual(desktop)
    fieldWidth = 680
    logoWidth = 380
    logoHeight = (logoWidth * 280) / 612
    fireEvent(window, new Event('resize'))
    expect(positions(field)).toEqual(desktop)
    expect(frames.size).toBe(1)
  })

  it('starts automatically and keeps orbiting with upright symbols and a centered logo', () => {
    const { field } = open()
    const initial = positions(field)
    expect(frames.size).toBe(1)
    nextFrame(0)
    for (let time = 16; time <= 1000; time += 16) nextFrame(time)
    expect(positions(field)).not.toEqual(initial)
    expect(positions(field).every((position) => !position.includes('rotate'))).toBe(true)
    expect(field).toHaveAttribute('data-logo-active', 'false')
    expect(screen.getByRole('img', { name: 'Tech News Radar' })).toBeInTheDocument()
    expect(frames.size).toBe(1)
  })

  it.each([' ', '{Enter}'])(
    'adds a keyboard wave with %s and returns to the moving orbit',
    async (key) => {
      const { field } = open()
      const control = open()
      nextFrame(0)
      field.focus()
      await userEvent.keyboard(key)
      for (let time = 16; time <= 640; time += 16) nextFrame(time)
      expect(positions(field)).not.toEqual(positions(control.field))
      for (let time = 656; time <= 5000; time += 16) nextFrame(time)
      expect(positions(field)).toEqual(positions(control.field))
      expect(frames.size).toBe(2)
    },
  )

  it('adds pointer repulsion to the orbit and enlarges the logo only over its desktop hit area', () => {
    const { field } = open()
    const control = open()
    nextFrame(0)
    fireEvent.pointerMove(field, { pointerType: 'mouse', clientX: 340, clientY: 165 })
    expect(field).toHaveAttribute('data-logo-active', 'true')
    fireEvent.pointerMove(field, { pointerType: 'mouse', clientX: 340, clientY: 24 })
    expect(field).toHaveAttribute('data-logo-active', 'false')
    for (let time = 16; time <= 320; time += 16) nextFrame(time)
    expect(positions(field)).not.toEqual(positions(control.field))
    fireEvent.pointerLeave(field)
    expect(field).toHaveAttribute('data-logo-active', 'false')
    for (let time = 336; time <= 5000; time += 16) nextFrame(time)
    expect(positions(field)).toEqual(positions(control.field))
  })

  it('keeps the logo stable on touch and narrow screens while taps create waves', () => {
    fieldWidth = 335
    logoWidth = fieldWidth * 0.64
    logoHeight = (logoWidth * 280) / 612
    const { field } = open()
    const control = open()
    nextFrame(0)
    fireEvent.pointerMove(field, { pointerType: 'touch', clientX: 167, clientY: 165 })
    fireEvent.pointerMove(field, { pointerType: 'mouse', clientX: 167, clientY: 165 })
    expect(field).toHaveAttribute('data-logo-active', 'false')
    expect(frames.size).toBe(2)
    fireEvent.click(field, { detail: 1, clientX: 167, clientY: 165 })
    for (let time = 16; time <= 640; time += 16) nextFrame(time)
    expect(positions(field)).not.toEqual(positions(control.field))
    expect(field).toHaveAttribute('data-logo-active', 'false')
  })

  it('respects reduced motion at startup and resumes automatically when the preference changes', () => {
    Object.defineProperty(motion, 'matches', { value: true, configurable: true })
    const { field, unmount } = open()
    const initial = positions(field)
    fireEvent.click(field)
    fireEvent.pointerMove(field, { pointerType: 'mouse', clientX: 340, clientY: 165 })
    expect(frames.size).toBe(0)
    expect(positions(field)).toEqual(initial)
    Object.defineProperty(motion, 'matches', { value: false })
    act(() => motionListeners.forEach((listener) => listener()))
    expect(frames.size).toBe(1)
    nextFrame(0)
    nextFrame(16)
    expect(positions(field)).not.toEqual(initial)
    const stopped = positions(field)
    Object.defineProperty(motion, 'matches', { value: true })
    act(() => motionListeners.forEach((listener) => listener()))
    expect(frames.size).toBe(0)
    expect(positions(field)).toEqual(stopped)
    unmount()
    expect(motionListeners.size).toBe(0)
  })

  it('pauses in a hidden tab and resumes without a time jump or duplicate loops', () => {
    const { field } = open()
    nextFrame(0)
    nextFrame(16)
    const stopped = positions(field)
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    fireEvent(document, new Event('visibilitychange'))
    expect(frames.size).toBe(0)
    expect(positions(field)).toEqual(stopped)
    hidden.mockReturnValue(false)
    fireEvent(document, new Event('visibilitychange'))
    fireEvent(document, new Event('visibilitychange'))
    expect(frames.size).toBe(1)
    nextFrame(60000)
    expect(positions(field)).toEqual(stopped)
    nextFrame(60016)
    expect(positions(field)).not.toEqual(stopped)
  })

  it('waits for visibility, pauses offscreen and resumes when the field reappears', () => {
    let onIntersection: (entries: { isIntersecting: boolean }[]) => void
    const disconnect = vi.fn()
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(callback: typeof onIntersection) {
          onIntersection = callback
        }
        observe = vi.fn()
        disconnect = disconnect
      },
    )
    const { field, unmount } = open()
    expect(frames.size).toBe(0)
    act(() => onIntersection([{ isIntersecting: true }]))
    expect(frames.size).toBe(1)
    nextFrame(0)
    nextFrame(16)
    const stopped = positions(field)
    act(() => onIntersection([{ isIntersecting: false }]))
    expect(frames.size).toBe(0)
    act(() => onIntersection([{ isIntersecting: true }]))
    nextFrame(60000)
    expect(positions(field)).toEqual(stopped)
    nextFrame(60016)
    expect(positions(field)).not.toEqual(stopped)
    unmount()
    expect(frames.size).toBe(0)
    expect(disconnect).toHaveBeenCalledTimes(2)
  })

  it('starts after the logo loads and cancels the loop when unmounted', () => {
    logoHeight = 0
    const { field, unmount } = open()
    expect(frames.size).toBe(0)
    expect(positions(field)).toHaveLength(0)
    logoHeight = (logoWidth * 280) / 612
    fireEvent.load(screen.getByRole('img', { name: 'Tech News Radar' }))
    expect(frames.size).toBe(1)
    unmount()
    expect(frames.size).toBe(0)
  })

  it('cancels pending animation when the access screen unmounts', () => {
    const { field, unmount } = open()
    fireEvent.click(field)
    expect(frames.size).toBe(1)
    unmount()
    expect(frames.size).toBe(0)
    expect(motionListeners.size).toBe(0)
  })
})
