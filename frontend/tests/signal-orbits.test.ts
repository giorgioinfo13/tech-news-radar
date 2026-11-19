import { describe, expect, it } from 'vitest'
import { advanceSignalOrbit, createSignalLayout } from '../src/signal-orbits'

describe('welcome signal orbits', () => {
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
    { width: 980, height: 380, imageWidth: 420 },
  ])(
    'completes clockwise turns clear of the logo and edges at $width × $height',
    ({ width, height, imageWidth }) => {
      const imageHeight = (imageWidth * 280) / 612
      const logoScale = width <= 440 ? 1 : 1.045
      const { orbits } = createSignalLayout(width, height, imageWidth, imageHeight)
      expect(orbits.length).toBeGreaterThanOrEqual(20)
      const previousAngles = orbits.map(({ baseX, baseY }) =>
        Math.atan2(baseY - height / 2, baseX - width / 2),
      )
      const angularTravel = orbits.map(() => 0)
      let violation: { step: number; index: number; x: number; y: number } | undefined

      // Exercise the production calculation at 30 fps for a full minute. Check
      // every coordinate on every frame, without thousands of DOM/style writes.
      for (let step = 0; step <= 1800; step++) {
        orbits.forEach((orbit, index) => {
          advanceSignalOrbit(orbit, step === 0 ? 0 : 1000 / 30, width, height)
          const { baseX: x, baseY: y } = orbit
          const outsideLogo =
            Math.abs(x - width / 2) >= (imageWidth * logoScale) / 2 + 8 ||
            Math.abs(y - height / 2) >= (imageHeight * logoScale) / 2 + 8
          const angle = Math.atan2(y - height / 2, x - width / 2)
          const change = angle - previousAngles[index]
          const travel = Math.atan2(Math.sin(change), Math.cos(change))
          angularTravel[index] += travel
          previousAngles[index] = angle
          if (
            !Number.isFinite(x) ||
            !Number.isFinite(y) ||
            x < 12 ||
            x > width - 12 ||
            y < 12 ||
            y > height - 12 ||
            !outsideLogo ||
            travel < -1e-9
          )
            violation ??= { step, index, x, y }
        })
      }

      expect(violation).toBeUndefined()
      // Bounds alone would also accept a static field: measure the actual path
      // around the center, independently of the production orbit formula.
      expect(Math.min(...angularTravel)).toBeGreaterThanOrEqual(2 * Math.PI - 0.01)
      if (width === 440 || width >= 980) {
        expect(Math.max(...angularTravel) - Math.min(...angularTravel)).toBeGreaterThan(0.5)
      }
    },
  )

  it('returns every symbol to its starting position after its own revolution', () => {
    const width = 980
    const height = 380
    const { orbits } = createSignalLayout(width, height, 420, (420 * 280) / 612)
    for (const orbit of orbits) {
      const { baseX, baseY } = orbit
      for (let step = 0; step < 1800; step++) {
        advanceSignalOrbit(orbit, orbit.period / 1800, width, height)
      }
      expect(orbit.baseX).toBeCloseTo(baseX, 6)
      expect(orbit.baseY).toBeCloseTo(baseY, 6)
    }
  })
})
