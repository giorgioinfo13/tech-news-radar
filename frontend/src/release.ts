declare const __RELEASE_NOTES__: string

// The newest release goes first, with one-line bullets under each language.
// Render plain text only; the notes never become executable HTML.
export function parseReleaseNotes(source: string) {
  const latest = source.replace(/\r\n/g, '\n').split(/^## /m)[1]
  if (!latest) throw new Error('Release notes must contain a version section')
  const version = latest.split('\n')[0].trim()
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Invalid release version')
  const sections = latest.split(/^### /m).slice(1)
  function changesFor(language: string) {
    const section = sections.find((part) => part.split('\n')[0].trim() === language)
    const changes = (section ?? '')
      .split('\n')
      .filter((line) => line.startsWith('- '))
      .map((line) => line.slice(2).replace(/\*\*/g, '').trim())
    if (!changes.length || changes.some((change) => !change)) {
      throw new Error(`Missing release notes for ${language}`)
    }
    return changes
  }
  return { version, changes: { it: changesFor('Italiano'), en: changesFor('English') } }
}

export const release = parseReleaseNotes(__RELEASE_NOTES__)

export const releaseStorageKey = (userId: string) => `tnr-whats-new-dismissed:${userId}`

export function shouldShowRelease(userId: string) {
  try {
    return localStorage.getItem(releaseStorageKey(userId)) !== release.version
  } catch {
    return true
  }
}
