import { expect, it } from 'vitest'
import { parseReleaseNotes, release } from '../src/release'

it('loads the bilingual release from the maintained notes', () => {
  expect(release.version).toBe('0.2.3')
  for (const changes of Object.values(release.changes)) {
    expect(changes.length).toBeGreaterThan(0)
    for (const change of changes) expect(change.trim()).not.toBe('')
  }
  expect(release.changes.it.join(' ')).toContain('Benvenuto interattivo.')
  expect(release.changes.en.join(' ')).toContain('Interactive welcome.')
  expect(release.changes.it.join(' ')).not.toContain('Rassegna AI.')
})

it('reads only the newest release and removes bold markers', () => {
  const notes =
    '# Notes\n\n## 1.2.3\n\n### Italiano\n- **Novità.** Testo\n\n### English\n- **News.** Text\n\n## 1.2.2\n### Italiano\n- Vecchio\n'
  expect(parseReleaseNotes(notes.replace(/\n/g, '\r\n'))).toEqual({
    version: '1.2.3',
    changes: { it: ['Novità. Testo'], en: ['News. Text'] },
  })
})

it('rejects incomplete notes', () => {
  expect(() => parseReleaseNotes('# Notes')).toThrow()
  expect(() => parseReleaseNotes('## invalid')).toThrow()
  expect(() => parseReleaseNotes('## 1.2.3\n### Italiano\n- Novità')).toThrow()
})
