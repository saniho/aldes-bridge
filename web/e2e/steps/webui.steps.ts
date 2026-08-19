import { createBdd } from 'playwright-bdd'
import { expect } from '@playwright/test'
import './parameter-types'

const { Given, When, Then } = createBdd()

// ---------------------------------------------------------------------------
//  Given : état initial de la WebUI
// ---------------------------------------------------------------------------

Given('le mode du bridge est à proxy', async ({ page }) => {
  const res = await page.request.post('/api/mode', { data: { mode: 'proxy' } })
  expect(res.ok()).toBeTruthy()
})

Given("l'historique des messages est vidé", async ({ page }) => {
  const res = await page.request.post('/api/clear')
  expect(res.ok()).toBeTruthy()
})

Given('le bridge sert la WebUI construite', async ({ page }) => {
  await page.addInitScript(() => {
    ;(window as unknown as Record<string, number>).__confirms = 0
    window.confirm = (() => {
      ;(window as unknown as Record<string, number>).__confirms++
      return true
    }).bind(window)
  })
  const res = await page.request.get('/api/config')
  expect(res.ok()).toBeTruthy()
})

Given('le bridge sert la WebUI construite avec confirmation refusée', async ({ page }) => {
  await page.addInitScript(() => {
    ;(window as unknown as Record<string, number>).__confirms = 0
    window.confirm = (() => {
      ;(window as unknown as Record<string, number>).__confirms++
      return false
    }).bind(window)
  })
  const res = await page.request.get('/api/config')
  expect(res.ok()).toBeTruthy()
})

// ---------------------------------------------------------------------------
//  When : actions utilisateur
// ---------------------------------------------------------------------------

When("j'ouvre la page d'accueil", async ({ page }) => {
  await page.goto('/')
})

When('je choisis le mode {texte} dans le sélecteur', async ({ page }, mode: string) => {
  await page.locator(`select:has(option[value="${mode}"])`).selectOption(mode)
})

// ---------------------------------------------------------------------------
//  Then : vérifications mode
// ---------------------------------------------------------------------------

Then('le titre de la page est {texte}', async ({ page }, title: string) => {
  await expect(page).toHaveTitle(title)
})

Then('la barre de statut affiche {texte}', async ({ page }, text: string) => {
  await expect(page.getByText(text, { exact: false })).toBeVisible({ timeout: 10000 })
})

Then('la barre de statut affiche toujours {texte}', async ({ page }, text: string) => {
  await expect(page.getByText(text, { exact: false })).toBeVisible({ timeout: 10000 })
})

Then('le sélecteur de mode propose {texte}', async ({ page }, mode: string) => {
  await expect(
    page.locator(`select:has(option[value="${mode}"])`)
  ).toBeVisible({ timeout: 10000 })
})

Then('une confirmation est demandée', async ({ page }) => {
  await expect
    .poll(() => page.evaluate(() => (window as unknown as Record<string, number>).__confirms))
    .toBeGreaterThan(0)
})

Then("j'accepte la confirmation", async () => {
  // la confirmation est déjà acceptée : le handler posé à l'ouverture renvoie true.
})

Then('je refuse la confirmation', async () => {
  // la confirmation est déjà refusée : le handler posé à l'ouverture renvoie false.
})

Then('le mode {texte} est actif côté API', async ({ page }, mode: string) => {
  const res = await page.request.get('/api/config')
  expect(res.ok()).toBeTruthy()
  const body = (await res.json()) as { mode: string }
  expect(body.mode).toBe(mode)
})

// ---------------------------------------------------------------------------
//  Then : vérifications messages
// ---------------------------------------------------------------------------

Then('la section des messages est visible', async ({ page }) => {
  await expect(page.locator('[class*="wrap"]').first()).toBeVisible({ timeout: 10000 })
})

Then('le compteur de messages affiche {texte}', async ({ page }, text: string) => {
  await expect(page.getByText(text)).toBeVisible({ timeout: 10000 })
})

Then('un texte par défaut est affiché dans les messages', async ({ page }) => {
  await expect(page.getByText('aucun message')).toBeVisible({ timeout: 10000 })
})
