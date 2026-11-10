import { expect, it } from 'vitest'
import { parseReleaseNotes, release } from '../release'

it('loads the bilingual release from the maintained notes', () => {
  expect(release.version).toBe('0.2.2')
  expect(release.changes.it).toHaveLength(6)
  expect(release.changes.en).toHaveLength(6)
  expect(release.changes.it.join(' ')).toContain('Rassegna AI.')
  expect(release.changes.it.join(' ')).toContain('Proponi una fonte.')
  expect(release.changes.it.join(' ')).not.toContain('Le novità del sito ti accolgono')
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
