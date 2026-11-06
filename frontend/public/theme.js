// Run before the page renders. Keep the storage contract aligned with Theme.tsx.
;(() => {
  let preference = 'system'
  try {
    const saved = localStorage.getItem('tnr-theme')
    if (saved === 'light' || saved === 'dark') preference = saved
  } catch {
    // Storage can be disabled; the system preference still works.
  }
  const dark =
    preference === 'dark' ||
    (preference === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', dark ? '#141e2b' : '#f4f6f8')
})()
