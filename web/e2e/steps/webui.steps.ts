import { createBdd, defineParameterType } from 'playwright-bdd'
import { expect } from '@playwright/test'

// Les arguments Gherkin sont ecrits en guillemets français « ... ».
defineParameterType({
  name: 'texte',
  regexp: /«([^»]*)»/,
  transformer: (s) => s.trim()
})

const { Given, When, Then } = createBdd()

// Compteur de confirmations vues par la page : posé dès l'ouverture pour ne
// jamais rater un dialog (un waitForEvent declare apres le declenchement
// manquerait la boite). Chaque confirm est acceptee pour laisser le flux
// continuer.
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

When('j\'ouvre la page d\'accueil', async ({ page }) => {
  await page.goto('/')
})

Then('le titre de la page est {texte}', async ({ page }, title: string) => {
  await expect(page).toHaveTitle(title)
})

Then('la barre de statut affiche {texte}', async ({ page }, text: string) => {
  await expect(page.getByText(text, { exact: false })).toBeVisible()
})

Then('le sélecteur de mode propose {texte}', async ({ page }, mode: string) => {
  await expect(
    page.locator(`select:has(option[value="${mode}"])`)
  ).toBeVisible()
})

When('je choisis le mode {texte} dans le sélecteur', async ({ page }, mode: string) => {
  await page.locator(`select:has(option[value="${mode}"])`).selectOption(mode)
})

Then('une confirmation est demandée', async ({ page }) => {
  await expect
    .poll(() => page.evaluate(() => (window as unknown as Record<string, number>).__confirms))
    .toBeGreaterThan(0)
})

Then('j\'accepte la confirmation', async () => {
  // la confirmation est déjà acceptée : le handler posé à l'ouverture renvoie true.
})

Then('le mode {texte} est actif côté API', async ({ page }, mode: string) => {
  const res = await page.request.get('/api/config')
  expect(res.ok()).toBeTruthy()
  const body = (await res.json()) as { mode: string }
  expect(body.mode).toBe(mode)
})