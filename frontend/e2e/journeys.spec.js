import { test, expect } from '@playwright/test'

const password = 'FixturePassword123!'

class SetupFlow {
  constructor(page) { this.page = page }
  async complete() {
    const page = this.page
    await page.goto('/')
    await page.getByLabel('Username', { exact: true }).fill('admin')
    await page.getByLabel('Email address', { exact: true }).fill('fixture@example.test')
    await page.getByLabel('Password (minimum 8 characters)', { exact: true }).fill(password)
    await page.getByLabel('Confirm password', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Create account', exact: true }).click()
    await expect(page.getByLabel('Media directory', { exact: true })).toBeVisible()
    for (const step of [3, 4, 5, 6, 7, 8, 9, 10]) {
      if (step === 5) await page.getByRole('checkbox', { name: /SABnzbd/ }).uncheck()
      if (step === 7) await expect(page.getByRole('checkbox', { name: /starter set of public/ })).not.toBeChecked()
      if (step === 10) {
        for (const checkbox of await page.locator('.wizard-options input[type="checkbox"]:checked').all()) await checkbox.uncheck()
      }
      await page.getByRole('button', { name: 'Next', exact: true }).click()
    }
    await page.getByRole('button', { name: 'Save & install', exact: true }).click()
    await expect(page.getByRole('searchbox', { name: 'Search', exact: true })).toBeVisible({ timeout: 30000 })
    await expect.poll(async () => (await this.state()).wired).toBe(true)
  }
  async state() { return (await this.page.request.get('/_test/state')).json() }
  async settings(section) { await this.page.goto(`/#/settings/${section}`); await expect(this.page.locator('.settings-header')).toBeVisible() }
}

test.beforeEach(async ({ request, page, baseURL }) => {
  await request.post('/_test/reset')
  // Test fixtures must never accidentally reach real provider hosts.
  const origin = new URL(baseURL).origin
  await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort())
})

async function assertFitsViewport(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
}

test('first installation → connection verification → request → download → library', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/provider-ready')
  await flow.settings('integrations')
  await page.getByRole('button', { name: 'Check connections', exact: true }).click()
  await expect(page.getByText('Library folders: pass', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('Search sources: pass', { exact: false })).toBeVisible()
  await expect(page.locator('.settings-content li strong').filter({ hasText: ': failed' })).toHaveCount(0)
  await assertFitsViewport(page)
  await page.goto('/#/home')
  await page.getByRole('searchbox', { name: 'Search', exact: true }).fill('Synthetic Journey')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByRole('button', { name: 'Get it now', exact: true }).click()
  await expect.poll(async () => (await flow.state()).requested).toBe(true)
  await page.reload()
  await expect(page.locator('.home-card').filter({ has: page.getByRole('heading', { name: 'Downloading', exact: true }) }).getByText('Synthetic Journey', { exact: true })).toBeVisible()
  const imported = await (await page.request.post('/_test/complete-download')).json()
  expect(imported.imported).toBe(true)
  await page.reload()
  await expect(page.locator('.home-card').filter({ has: page.getByRole('heading', { name: 'Recently added', exact: true }) }).getByText('Synthetic Journey', { exact: true })).toBeVisible()
  await assertFitsViewport(page)
})

test('backup and selective restore preserve the original application configuration', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await flow.settings('backups')
  await page.getByRole('button', { name: 'Backup now', exact: true }).click()
  const list = page.locator('.backup-list')
  await expect(list.getByRole('button', { name: 'Restore', exact: true }).first()).toBeVisible()
  await page.request.post('/_test/change-preferences')
  expect((await flow.state()).preferences.quality).toBe('changed')
  await list.getByRole('button', { name: 'Restore', exact: true }).first().click()
  await page.locator('.backup-restore').getByRole('checkbox', { name: 'sonarr', exact: true }).check()
  page.once('dialog', dialog => dialog.accept())
  await page.locator('.backup-restore').getByRole('button', { name: 'Restore', exact: true }).click()
  await expect.poll(async () => (await flow.state()).preferences.quality).toBe('original')
  await expect(page.locator('[role="alert"]')).toHaveCount(0)
  await assertFitsViewport(page)
})

test('failed update restores settings and reports rollback without a success toast', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/fail-update')
  await page.goto('/#/catalog')
  await page.getByRole('button', { name: 'More actions for Sonarr', exact: true }).click()
  await page.locator('.card-menu').getByRole('button', { name: 'Update', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Ready to proceed? — sonarr' })).toBeVisible()
  const completed = page.waitForResponse(response => response.url().endsWith('/api/applications/sonarr/update') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  const response = await completed
  expect(response.ok()).toBe(true)
  const outcome = await response.json()
  expect(outcome.status).toBe('rolled_back')
  expect(outcome.recovery).toEqual({ binary: true, configuration: true, process: true })
  expect((await flow.state()).preferences.quality).toBe('original')
  await expect(page.getByText('Update failed; previous version restored: Synthetic update failure', { exact: true })).toBeVisible()
  await expect(page.locator('.toast-success')).toHaveCount(0)
  await page.getByRole('button', { name: 'Installation activity', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('sonarr — rolled_back', { exact: true })).toBeVisible()
  await expect(page.getByRole('dialog').getByText(/previous version restored/).first()).toBeVisible()
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  await assertFitsViewport(page)
})

test('notification form still saves after moving between settings sections', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await flow.settings('notifications')
  await page.getByLabel('Warn above (%)', { exact: true }).fill('82')
  await page.getByLabel('Recovered below (%)', { exact: true }).fill('75')
  await page.locator('form').filter({ has: page.getByRole('heading', { name: 'Storage warning thresholds' }) }).getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByText('Notifications saved.', { exact: true })).toBeVisible()
  await flow.settings('account')
  await flow.settings('notifications')
  await expect(page.getByLabel('Warn above (%)', { exact: true })).toHaveValue('82')
  await expect(page.getByLabel('Recovered below (%)', { exact: true })).toHaveValue('75')
  await assertFitsViewport(page)
})


test('calendar controls preserve a manually selected view across viewport changes', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  const calendar = page.locator('.home-card-calendar')
  await expect(calendar).toBeVisible()
  await calendar.getByRole('button', { name: 'Calendar view', exact: true }).click()
  await page.getByRole('option', { name: 'Month', exact: true }).click()
  await expect(calendar.locator('.cal-mode-month')).toBeVisible()
  const today = calendar.getByRole('button', { name: 'Today', exact: true })
  if (await today.isVisible()) await today.click()
  await expect(calendar.getByText('Calendar fixture', { exact: true })).toBeVisible()
  const viewport = page.viewportSize()
  await page.setViewportSize({ width: viewport.width < 600 ? 1100 : 390, height: viewport.height })
  await expect(calendar.locator('.cal-mode-month')).toBeVisible()
  await page.setViewportSize(viewport)
  await assertFitsViewport(page)
})


test('header navigation stays centered, scrolls away and uses the Home typeface everywhere', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Edit the Home layout', exact: true })).toHaveCount(0)
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.route('**/api/updates/status', route => route.fulfill({ json: { available: [{ name: 'sonarr', latest_version: '2.0.0' }], notify_enabled: false } }))
  for (const width of [1440, 1100, 960, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    for (const route of ['home', 'catalog', 'settings/account']) {
      await page.goto(`/#/${route}`)
      await expect(page.locator('.nav-tabs')).toBeVisible()
      await page.locator('.nav-tabs a').last().waitFor()
      const geometry = await page.locator('.top-nav').evaluate(header => {
        const nav = header.querySelector('.nav-tabs'), h = header.getBoundingClientRect(), n = nav.getBoundingClientRect()
        return { delta: Math.abs((n.left + n.right) / 2 - (h.left + h.right) / 2), position: getComputedStyle(header).position, fonts: [...nav.querySelectorAll('a')].map(node => getComputedStyle(node).fontFamily) }
      })
      expect(geometry.delta).toBeLessThan(1)
      expect(geometry.position).toBe('relative')
      expect(geometry.fonts.every(font => font === geometry.fonts[0])).toBe(true)
      await assertFitsViewport(page)
    }
  }
  await flow.settings('backups')
  const typography = await page.evaluate(() => ({ body: getComputedStyle(document.body).fontFamily, controls: [...document.querySelectorAll('input, button, textarea, select, code, pre, .font-mono')].filter(node => node.getClientRects().length).map(node => getComputedStyle(node).fontFamily) }))
  expect(typography.controls.every(font => font === typography.body)).toBe(true)
  await page.evaluate(() => { document.body.style.minHeight = '2500px'; window.scrollTo(0, 600) })
  await expect.poll(async () => page.locator('.top-nav').evaluate(node => node.getBoundingClientRect().bottom)).toBeLessThan(0)
})
