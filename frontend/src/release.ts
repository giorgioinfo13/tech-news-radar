export const release = {
  version: '0.2.0',
  changes: {
    it: [
      'Le novità del sito ti accolgono all’apertura. Puoi nasconderle per questa versione e ritrovarle dal menu.',
      'Il numero di versione è ora visibile in fondo al menu.',
    ],
    en: [
      'See what’s new when you open the site. You can hide these notes for this version and reopen them from the menu.',
      'The version number is now shown at the bottom of the menu.',
    ],
  },
} as const

export const releaseStorageKey = (userId: string) => `tnr-whats-new-dismissed:${userId}`

export function shouldShowRelease(userId: string) {
  try {
    return localStorage.getItem(releaseStorageKey(userId)) !== release.version
  } catch {
    return true
  }
}
