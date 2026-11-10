import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  define: {
    __RELEASE_NOTES__: JSON.stringify(
      readFileSync(new URL('../RELEASES NOTES.md', import.meta.url), 'utf8'),
    ),
  },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], restoreMocks: true },
})
