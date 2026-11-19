export type SignalOrbit = {
  index: number
  ring: number
  opacity: number
  angle: number
  radiusX: number
  radiusY: number
  period: number
  baseX: number
  baseY: number
}

export function advanceSignalOrbit(
  orbit: SignalOrbit,
  elapsed: number,
  width: number,
  height: number,
) {
  orbit.angle = (orbit.angle + (elapsed * 2 * Math.PI) / orbit.period) % (2 * Math.PI)
  const cos = Math.cos(orbit.angle)
  const sin = Math.sin(orbit.angle)
  // A rounded orbit leaves space for the wide logo without clipping its corners.
  const scale = (cos ** 4 + sin ** 4) ** -0.25
  orbit.baseX = width / 2 + orbit.radiusX * cos * scale
  orbit.baseY = height / 2 + orbit.radiusY * sin * scale
}

export function createSignalLayout(
  width: number,
  height: number,
  logoWidth: number,
  logoHeight: number,
) {
  const mobile = width <= 440
  const inset = mobile ? 14 : 20
  const outerRadiusX = width / 2 - inset
  const outerRadiusY = height / 2 - inset
  const logoScale = mobile ? 1 : 1.045
  // 2^(1/4) encloses all four corners of the logo, including the hover enlargement.
  const innerRadiusX = ((logoWidth * logoScale) / 2 + 10) * 2 ** 0.25
  const innerRadiusY = ((logoHeight * logoScale) / 2 + 12) * 2 ** 0.25
  const orbits: SignalOrbit[] = []
  const layout = { innerRadiusX, innerRadiusY, orbits }
  // Wait for a usable layout rather than placing symbols on top of the logo.
  if (innerRadiusX > outerRadiusX || innerRadiusY > outerRadiusY) return layout
  const room = Math.min(outerRadiusX - innerRadiusX, outerRadiusY - innerRadiusY)
  const rings = Math.min(mobile ? 2 : 4, Math.floor(room / 24) + 1)
  for (let ring = 0; ring < rings; ring++) {
    const fraction = rings === 1 ? 0.5 : ring / (rings - 1)
    const radiusX = innerRadiusX + (outerRadiusX - innerRadiusX) * fraction
    const radiusY = innerRadiusY + (outerRadiusY - innerRadiusY) * fraction
    const count = Math.min(
      mobile ? 28 : 56,
      Math.floor((2 * Math.PI * Math.min(radiusX, radiusY)) / 28),
    )
    for (let index = 0; index < count; index++) {
      const orbit = {
        index,
        ring,
        opacity: 0.78 - fraction * 0.28,
        angle: 2 * Math.PI * (index / count + ring * 0.137),
        radiusX,
        radiusY,
        period: (mobile ? 54000 : 42000) + ring * 6000,
        baseX: 0,
        baseY: 0,
      }
      advanceSignalOrbit(orbit, 0, width, height)
      orbits.push(orbit)
    }
  }
  return layout
}
