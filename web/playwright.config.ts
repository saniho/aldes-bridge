import { defineConfig } from '@playwright/test'
import { defineBddConfig } from 'playwright-bdd'

// playwright-bdd : les tests E2E sont ecrits en Gherkin (e2e/features/*.feature)
// et leurs definitions de pas en TypeScript (e2e/steps/*.ts). Le testDir est
// genere par playwright-bdd a partir de ces deux sources.
const testDir = defineBddConfig({
  features: 'e2e/features/**/*.feature',
  steps: 'e2e/steps/**/*.ts'
})

const WEB_PORT = 18080
const MQTT_PORT = 18884
const BASE_URL = `http://127.0.0.1:${WEB_PORT}`

export default defineConfig({
  testDir,
  // Les scénarios partagent un backend dont le mode est un état global mutable.
  // Leur exécution concurrente permet à un scénario de réinitialiser le mode
  // pendant qu'un autre le vérifie côté API.
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry'
  },
  // La WebUI testee est la vraie (web/dist construit + API du bridge python
  // tournant localement avec un faux Azure : aucune box reelle requise).
  webServer: {
    command:
      `npm run build && cd .. && ` +
      `python3 -m server.main --web-port ${WEB_PORT} --mqtt-port ${MQTT_PORT} ` +
      `--mode proxy --mode-file /tmp/aldes-e2e/mode.json ` +
      `--log-file "" --telemetry-file "" --consigne-file ""`,
    url: `${BASE_URL}/api/config`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }]
})
