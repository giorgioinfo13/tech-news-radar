import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'
import { release } from '../release'

// jsdom does not implement the native modal focus/top-layer behavior.
HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '')
}
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open')
}

beforeEach(() => {
  const getItem = Storage.prototype.getItem
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (this: Storage, key: string) {
    return key.startsWith('tnr-whats-new-dismissed:') ? release.version : getItem.call(this, key)
  })
  localStorage.removeItem('tnr-language')
  document.documentElement.lang = 'it'
  vi.stubEnv('VITE_LOCAL_MODE', 'true')
  vi.stubEnv('VITE_SUPABASE_URL', '')
  vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', '')
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.removeItem('tnr-language')
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  history.replaceState(null, '', '/#news')
})
