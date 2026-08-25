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

Given('les paramètres sont réinitialisés', async ({ page }) => {
  const res = await page.request.put('/api/settings', {
    data: { history_retention_days: 90, log_retention_max_bytes: 26214400 }
  })
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

When('je clique sur l\'onglet {texte}', async ({ page }, label: string) => {
  await page.getByRole('tab', { name: label, exact: false }).click()
})

When('je clique sur le menu burger', async ({ page }) => {
  await page.locator('button.burger').click()
})

When('je bascule le thème', async ({ page }) => {
  const moreMenu = page.locator('.moreMenu')
  if (!(await moreMenu.isVisible().catch(() => false))) {
    await page.locator('button.burger').click()
  }
  await expect(moreMenu).toBeVisible({ timeout: 5000 })
  await page.getByText('passer en mode').click()
})

When('je clique sur {texte}', async ({ page }, label: string) => {
  await page.getByRole('button', { name: label, exact: false }).click()
})

When('je clique sur l\'item de menu {texte}', async ({ page }, label: string) => {
  await page.getByRole('menuitem', { name: label, exact: false }).click()
})

When('des messages MQTT sont injectés', async ({ page }) => {
  const res = await page.request.post('/api/test/inject', {
    data: { topic: 'aldes/test', payload: '{"test":true}', qos: 0 }
  })
  expect(res.ok()).toBeTruthy()
})

When('des télémétries numériques sont injectées', async ({ page }) => {
  for (const v of [21.5, 21.8, 22.1]) {
    const res = await page.request.post('/api/test/inject', {
      data: { topic: 'aldes/telemetry', payload: `{"Text":${v},"MT0":24.0}`, qos: 0 }
    })
    expect(res.ok()).toBeTruthy()
  }
})

When('je tape {texte} dans la recherche', async ({ page }, text: string) => {
  await page.locator('input[placeholder="rechercher…"]').fill(text)
})

When('je sélectionne le filtre de direction {texte}', async ({ page }, label: string) => {
  await page.locator('select').nth(1).selectOption({ label })
})

When('je sélectionne le filtre de type {texte}', async ({ page }, label: string) => {
  await page.locator('select').nth(2).selectOption({ label })
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
//  Then : vérifications navigation
// ---------------------------------------------------------------------------

Then('l\'onglet {texte} est actif', async ({ page }, label: string) => {
  await expect(page.getByRole('tab', { name: label, exact: false })).toHaveAttribute(
    'aria-selected',
    'true'
  )
})

Then('aucun onglet n\'est actif', async ({ page }) => {
  const tabs = page.getByRole('tab')
  const count = await tabs.count()
  for (let i = 0; i < count; i++) {
    await expect(tabs.nth(i)).toHaveAttribute('aria-selected', 'false')
  }
})

Then('le menu burger est ouvert', async ({ page }) => {
  await expect(page.locator('.moreMenu')).toBeVisible()
})

Then('le menu burger est fermé', async ({ page }) => {
  await expect(page.locator('.moreMenu')).not.toBeVisible()
})

// ---------------------------------------------------------------------------
//  Then : vérifications thème
// ---------------------------------------------------------------------------

Then('la WebUI est en mode nuit', async ({ page }) => {
  await expect(page.locator('html')).not.toHaveAttribute('data-theme', 'jour')
})

Then('la WebUI est en mode jour', async ({ page }) => {
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'jour')
})

// ---------------------------------------------------------------------------
//  Then : vérifications déconnexion
// ---------------------------------------------------------------------------

Then('le bouton déconnecter est visible', async ({ page }) => {
  await expect(page.getByRole('button', { name: /déconnecter/i })).toBeVisible()
})

Then('le bouton déconnecter n\'est pas visible', async ({ page }) => {
  await expect(page.getByRole('button', { name: /déconnecter/i })).not.toBeVisible()
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

Then('le compteur de messages affiche au moins une valeur', async ({ page }) => {
  const countEl = page.locator('[class*="count"]').first()
  await expect(countEl).toBeVisible({ timeout: 10000 })
  const text = await countEl.textContent()
  if (!/^\d+\s*\/\s*\d+$/.test(text?.trim() ?? '')) {
    throw new Error(`Counter "${text}" does not match N / N pattern`)
  }
  const filtered = parseInt(text!.split('/')[0].trim(), 10)
  if (filtered < 1) throw new Error(`Expected ≥1 message, got ${filtered}`)
})

Then('le compteur de messages filtrés affiche zéro', async ({ page }) => {
  const countEl = page.locator('[class*="count"]').first()
  await expect(countEl).toHaveText(/^0\s*\/\s*\d+$/, { timeout: 10000 })
})

Then('un texte par défaut est affiché dans les messages', async ({ page }) => {
  await expect(page.getByText('aucun message')).toBeVisible({ timeout: 10000 })
})

Then('un message est affiché dans le flux', async ({ page }) => {
  await expect(page.getByText('aldes/test')).toBeVisible({ timeout: 10000 })
})

Then('le badge BLOQUÉ est visible', async ({ page }) => {
  await expect(page.getByText('BLOQUÉ')).toBeVisible({ timeout: 10000 })
})

Then('la légende affiche {texte}', async ({ page }, text: string) => {
  await expect(page.getByText(text, { exact: false })).toBeVisible({ timeout: 10000 })
})

Then('les versions UI et Backend sont affichées', async ({ page }) => {
  const versionEl = page.locator('.moreVersion')
  await expect(versionEl).toBeVisible({ timeout: 10000 })
  await expect(versionEl).toContainText(/UI v\d+\.\d+\.\d+/, { timeout: 10000 })
  await expect(versionEl).toContainText(/Backend v\d+\.\d+\.\d+/, { timeout: 10000 })
})

// ---------------------------------------------------------------------------
//  Then : vérifications historique
// ---------------------------------------------------------------------------

Then('le panneau historique est visible', async ({ page }) => {
  await expect(page.getByText('Historique des valeurs')).toBeVisible({ timeout: 10000 })
})

Then('une valeur historique est affichée', async ({ page }) => {
  await expect(page.getByLabel('Capteur')).toBeVisible({ timeout: 10000 })
  const chart = page.locator('.recharts-wrapper').first()
  await expect(chart).toBeVisible({ timeout: 15000 })
})

// ---------------------------------------------------------------------------
//  Then : vérifications config panel
// ---------------------------------------------------------------------------

Then('le panneau de configuration est visible', async ({ page }) => {
  await expect(page.getByText('Configuration')).toBeVisible({ timeout: 10000 })
})

Then('le champ rétention historique affiche {texte}', async ({ page }, value: string) => {
  const input = page.locator('input[type="number"]')
  await expect(input).toBeVisible({ timeout: 10000 })
  await expect(input).toHaveValue(value)
})

Then('le champ taille max logs affiche {texte}', async ({ page }, value: string) => {
  const input = page.locator('input[type="text"]')
  await expect(input).toBeVisible({ timeout: 10000 })
  await expect(input).toHaveValue(value)
})

Then('un message de confirmation est affiché', async ({ page }) => {
  await expect(page.getByText('Sauvegarde')).toBeVisible({ timeout: 5000 })
})

Then('la rétention historique est {texte} côté API', async ({ page }, days: string) => {
  const res = await page.request.get('/api/settings')
  expect(res.ok()).toBeTruthy()
  const body = (await res.json()) as { settings: { history_retention_days: number } }
  expect(body.settings.history_retention_days).toBe(parseInt(days, 10))
})

// ---------------------------------------------------------------------------
//  When : actions config panel
// ---------------------------------------------------------------------------

When('je tape {texte} dans le champ rétention historique', async ({ page }, value: string) => {
  const input = page.locator('input[type="number"]')
  await input.fill(value)
})

// ---------------------------------------------------------------------------
//  Then : vérifications profil selector
// ---------------------------------------------------------------------------

Then('le sélecteur de profil est visible', async ({ page }) => {
  await expect(page.locator('select').filter({ has: page.locator('option') }).first()).toBeVisible({ timeout: 10000 })
})

Then('le profil sélectionné est {texte}', async ({ page }, name: string) => {
  const select = page.locator('.profileSelect, select').filter({ hasText: name }).first()
  await expect(select).toBeVisible({ timeout: 10000 })
  await expect(select).toHaveValue(/tone-aquaair/)
})

Then('le profil {texte} est actif côté API', async ({ page }, profileId: string) => {
  const res = await page.request.get('/api/profile')
  expect(res.ok()).toBeTruthy()
  const body = (await res.json()) as { profile: { id: string } | null }
  expect(body.profile?.id).toBe(profileId)
})

// ---------------------------------------------------------------------------
//  When : actions profil selector
// ---------------------------------------------------------------------------

When('je change le profil pour {texte}', async ({ page }, profileId: string) => {
  const select = page.locator('.profileSelect, select').filter({ has: page.locator(`option[value="${profileId}"]`) }).first()
  await select.selectOption(profileId)
})
