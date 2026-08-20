import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const rootDir = dirname(fileURLToPath(import.meta.url))

// Écrit dist/version.json {"ui": "<version package.json>"} à la fin du build :
// le backend le lit (server/version.py) pour exposer la version UI servie.
function uiVersionPlugin(): Plugin {
  return {
    name: 'ui-version',
    apply: 'build',
    writeBundle() {
      const pkg = JSON.parse(readFileSync(join(rootDir, 'package.json'), 'utf8'))
      const outDir = join(rootDir, 'dist')
      mkdirSync(outDir, { recursive: true })
      writeFileSync(join(outDir, 'version.json'), JSON.stringify({ ui: pkg.version }, null, 2))
    }
  }
}

export default defineConfig({
  plugins: [react(), uiVersionPlugin()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080'
    }
  }
})