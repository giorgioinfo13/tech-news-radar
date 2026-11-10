import { fileURLToPath } from 'node:url'
import { readFileSync } from 'node:fs'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

const projectRoot = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, projectRoot, 'TNR_')

  return {
    plugins: [react(), tailwindcss()],
    define: {
      __RELEASE_NOTES__: JSON.stringify(
        readFileSync(new URL('../RELEASES NOTES.md', import.meta.url), 'utf8'),
      ),
    },
    envDir: projectRoot,
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: env.TNR_API_TARGET || 'http://127.0.0.1:8000',
        },
      },
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
      strictPort: true,
    },
  }
})
