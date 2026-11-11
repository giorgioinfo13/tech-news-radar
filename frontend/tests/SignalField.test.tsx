import { StrictMode } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
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
  logoWidth = 260
  logoHeight = 111
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

function nextFrame(time: number) {
  act(() => {
    const pending = [...frames.values()]
    frames.clear()
    pending.forEach((callback) => callback(time))
  })
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
  const field = screen.getByRole('button', { name: /Tech News Radar: segnali interattivi/ })
  return { ...view, field }
}

describe('interactive welcome signals', () => {
  it.each([265, 350, 390, 440])(
    'keeps two populated arcs clear of the large logo at %ipx',
    (width) => {
      fieldWidth = width
      fieldHeight = 310
      logoWidth = Math.min(320, width * 0.88)
      logoHeight = (logoWidth * 280) / 612
      const { field } = open()
      const points = positions(field).map((transform) => {
        const [, x, y] = transform.match(/translate\(([\d.-]+)px, ([\d.-]+)px\)/)!
        return { x: Number(x), y: Number(y) }
      })
      expect(points.filter(({ y }) => y < fieldHeight / 2).length).toBeGreaterThanOrEqual(15)
      expect(points.filter(({ y }) => y > fieldHeight / 2).length).toBeGreaterThanOrEqual(15)
      for (const point of points) {
        expect(point.x).toBeGreaterThanOrEqual(8)
        expect(point.x).toBeLessThanOrEqual(width - 8)
        expect(point.y).toBeGreaterThanOrEqual(8)
        expect(point.y).toBeLessThanOrEqual(fieldHeight - 8)
        const outsideLogo =
          Math.abs(point.x - width / 2) >= logoWidth / 2 + 8 ||
          Math.abs(point.y - fieldHeight / 2) >= logoHeight / 2 + 8
        expect(outsideLogo).toBe(true)
        for (const other of points) {
          if (point !== other)
            expect(Math.hypot(point.x - other.x, point.y - other.y)).toBeGreaterThan(18)
        }
      }
    },
  )

  it('restores the desktop field after resizing through the mobile layout', () => {
    const { field } = open()
    const desktop = positions(field)
    fieldWidth = 350
    fireEvent(window, new Event('resize'))
    expect(positions(field)).not.toEqual(desktop)
    fieldWidth = 680
    fireEvent(window, new Event('resize'))
    expect(positions(field)).toEqual(desktop)
  })

  it('stays still until interaction, supports keyboard waves and settles afterwards', async () => {
    const { field } = open()
    const initial = positions(field)
    expect(initial.length).toBeGreaterThan(0)
    expect(frames.size).toBe(0)
    field.focus()
    await userEvent.keyboard(' ')
    nextFrame(100)
    expect(positions(field)).not.toEqual(initial)
    for (let time = 116; time < 4000; time += 16) nextFrame(time)
    expect(frames.size).toBe(0)
    expect(screen.getByRole('img', { name: 'Tech News Radar' })).toBeInTheDocument()
  })

  it('enlarges the logo only over its desktop hit area and restores it on leaving', () => {
    const { field } = open()
    fireEvent.pointerMove(field, { pointerType: 'mouse', clientX: 340, clientY: 165 })
    expect(field).toHaveAttribute('data-logo-active', 'true')
    fireEvent.pointerMove(field, { pointerType: 'mouse', clientX: 50, clientY: 40 })
    expect(field).toHaveAttribute('data-logo-active', 'false')
    const initial = positions(field)
    nextFrame(16)
    expect(positions(field)).not.toEqual(initial)
    fireEvent.pointerLeave(field)
    expect(field).toHaveAttribute('data-logo-active', 'false')
  })

  it('keeps the logo stable on touch and narrow screens while taps create waves', () => {
    fieldWidth = 335
    const { field } = open()
    const initial = positions(field)
    fireEvent.pointerMove(field, { pointerType: 'touch', clientX: 167, clientY: 165 })
    fireEvent.pointerMove(field, { pointerType: 'mouse', clientX: 167, clientY: 165 })
    expect(field).toHaveAttribute('data-logo-active', 'false')
    expect(frames.size).toBe(0)
    fireEvent.click(field, { detail: 1, clientX: 167, clientY: 165 })
    nextFrame(100)
    expect(positions(field)).not.toEqual(initial)
    expect(field).toHaveAttribute('data-logo-active', 'false')
  })

  it('respects reduced motion at startup and when the system preference changes', () => {
    Object.defineProperty(motion, 'matches', { value: true, configurable: true })
    const { field, unmount } = open()
    const initial = positions(field)
    fireEvent.click(field)
    fireEvent.pointerMove(field, { pointerType: 'mouse', clientX: 340, clientY: 165 })
    expect(frames.size).toBe(0)
    expect(positions(field)).toEqual(initial)
    Object.defineProperty(motion, 'matches', { value: false })
    act(() => motionListeners.forEach((listener) => listener()))
    fireEvent.click(field)
    nextFrame(100)
    expect(positions(field)).not.toEqual(initial)
    Object.defineProperty(motion, 'matches', { value: true })
    act(() => motionListeners.forEach((listener) => listener()))
    expect(frames.size).toBe(0)
    expect(positions(field)).toEqual(initial)
    unmount()
    expect(motionListeners.size).toBe(0)
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
