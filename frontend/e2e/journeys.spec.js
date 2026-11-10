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
        // Keep indices stable as checkboxes change state during the loop.
        for (const checkbox of await page.locator('.wizard-options input[type="checkbox"]').all()) await checkbox.uncheck()
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

test('Cleanuparr appears in the catalog with setup guidance and a private recovery key field', async ({ page }, testInfo) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.goto('/#/catalog')
  await page.getByPlaceholder('Search apps…').fill('Cleanuparr')
  const app = page.locator('.catalog-store-app').filter({ hasText: 'Cleanuparr' })
  await expect(app).toHaveCount(1)
  const icon = app.locator('img')
  await expect.poll(() => icon.evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true)
  await page.getByRole('button', { name: 'Settings for Cleanuparr', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText(/New setups start in dry-run/)).toBeVisible()
  await expect(dialog.getByLabel('Cleanuparr API key', { exact: true })).toHaveAttribute('type', 'password')
  await expect(dialog.getByRole('spinbutton')).toHaveValue('11011')
  await assertFitsViewport(page)
  for (const theme of ['dark', 'light']) {
    await page.evaluate(value => document.documentElement.setAttribute('data-theme', value), theme)
    await page.screenshot({ path: testInfo.outputPath(`cleanuparr-settings-${theme}.png`), fullPage: true })
  }
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
})

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
      await expect(page.locator('.nav-tabs .nav-edit-btn')).toHaveCount(route === 'home' ? 1 : 0)
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

test('trending requests are only available in the poster dialog', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/trending')
  await page.reload()
  const tile = page.locator('.home-tile-trending').filter({ hasText: 'Trending Fixture' })
  await expect(tile).toBeVisible()
  await expect(tile.locator('.home-tile-request')).toHaveCount(0)
  await tile.locator('.home-tile-link').click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Trending Fixture', exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Request', exact: true })).toBeVisible()
})

test('trending popup keeps request available when title details fail', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/trending')
  await page.request.post('/_test/trending-detail-fail')
  await page.reload()
  await page.locator('.home-tile-trending').filter({ hasText: 'Trending Fixture' }).locator('.home-tile-link').click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Synthetic title detail failure', { exact: true })).toBeVisible()
  const request = dialog.getByRole('button', { name: 'Request', exact: true })
  await expect(request).toBeVisible()
  await request.click()
  await expect.poll(async () => (await flow.state()).requested).toBe(true)
})

test('trending shows poster dots only for available and requested titles', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/trending-statuses')
  await page.reload()
  const tile = (title) => page.locator('.home-tile-trending').filter({ hasText: title })
  await expect(tile('Available Trending').locator('.home-status-dot.is-available')).toHaveCount(1)
  await expect(tile('Requested Trending').locator('.home-status-dot.is-requested')).toHaveCount(1)
  await expect(tile('Missing Trending').locator('.home-status-dot')).toHaveCount(0)
})

test('calendar colors use the app source unless the item is available', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/calendar-colors')
  await page.reload()
  const calendar = page.locator('.home-card-calendar')
  await calendar.getByRole('button', { name: 'Calendar view', exact: true }).click()
  await page.getByRole('option', { name: 'Month', exact: true }).click()
  const colors = await calendar.evaluate((root) => {
    const resolve = (value) => {
      const probe = document.createElement('span')
      probe.style.color = value
      root.append(probe)
      const color = getComputedStyle(probe).color
      probe.remove()
      return color
    }
    const eventColor = (selector) => getComputedStyle(root.querySelector(selector)).borderLeftColor
    return {
      sonarr: eventColor('.cal-event[data-source="sonarr"]'),
      radarr: eventColor('.cal-event[data-source="radarr"]'),
      available: eventColor('.cal-event.is-have'),
      info: resolve('var(--color-info)'),
      radarrToken: resolve('var(--calendar-radarr-color)'),
      success: resolve('var(--color-success)'),
    }
  })
  expect(colors.sonarr).toBe(colors.info)
  expect(colors.radarr).toBe(colors.radarrToken)
  expect(colors.available).toBe(colors.success)

  await calendar.getByRole('button', { name: 'Calendar view', exact: true }).click()
  await page.getByRole('option', { name: 'List', exact: true }).click()
  const listColors = await calendar.evaluate((root) => {
    const rowColor = (selector) => getComputedStyle(root.querySelector(`${selector} .cal-row-link`)).borderLeftColor
    return {
      sonarr: rowColor('.cal-row[data-source="sonarr"]'),
      radarr: rowColor('.cal-row[data-source="radarr"]'),
      available: rowColor('.cal-row.is-have'),
    }
  })
  expect(listColors.sonarr).toBe(colors.info)
  expect(listColors.radarr).toBe(colors.radarrToken)
  expect(listColors.available).toBe(colors.success)
})

test('media widgets and posters share dimensions and service status uses one dot', async ({ page }, testInfo) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/media-widgets')
  await page.request.post('/_test/service-status')
  await page.reload()

  const widgets = ['recent', 'requests', 'trending'].map((id) => page.locator(`.hg-item[data-widget="${id}"]`))
  for (const widget of widgets) {
    await expect(widget).toBeVisible()
    await expect(widget.locator('.home-tile')).toHaveCount(2)
  }
  const bounds = await Promise.all(widgets.map((widget) => widget.boundingBox()))
  for (const value of ['width', 'height']) {
    expect(Math.abs(bounds[0][value] - bounds[1][value])).toBeLessThan(1)
    expect(Math.abs(bounds[1][value] - bounds[2][value])).toBeLessThan(1)
  }
  await page.screenshot({ path: testInfo.outputPath('media-widgets.png'), fullPage: true })
  const posters = await Promise.all(widgets.map((widget) => widget.locator('.home-tile-poster').first().boundingBox()))
  for (const value of ['width', 'height']) {
    expect(Math.abs(posters[0][value] - posters[1][value])).toBeLessThan(1)
    expect(Math.abs(posters[1][value] - posters[2][value])).toBeLessThan(1)
  }

  const status = page.locator('.nav-account-status')
  await expect(status.locator('.status-dot')).toHaveCount(1)
  await expect(status.locator('.status-chip')).toHaveAttribute('data-tone', 'ok')
  await page.request.post('/_test/service-status-down')
  await page.reload()
  await expect(status.locator('.status-dot')).toHaveCount(1)
  await expect(status.locator('.status-chip')).toHaveAttribute('data-tone', 'bad')
})

test('Home grid keeps pointer drag, resize and keyboard controls with glass styling', async ({ page }, testInfo) => {
  await new SetupFlow(page).complete()
  await page.getByRole('button', { name: 'Edit the Home layout', exact: true }).click()
  const item = page.locator('.hg-item[data-widget="greeting"]')
  const initialLabel = await item.getAttribute('aria-label')
  const grip = await item.locator('.hg-grip').boundingBox()
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2)
  await page.mouse.down()
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2 + 115, { steps: 10 })
  await expect(item).toHaveClass(/is-lifted/)
  await expect(item).toHaveCSS('z-index', '30')
  await page.mouse.up()
  await expect(item).not.toHaveClass(/is-lifted/)
  await expect(item).not.toHaveAttribute('aria-label', initialLabel)
  await item.scrollIntoViewIfNeeded()
  const beforeResize = await item.getAttribute('aria-label')
  const corner = await item.locator('.hg-rz').boundingBox()
  await page.mouse.move(corner.x + corner.width / 2, corner.y + corner.height / 2)
  await page.mouse.down()
  await page.mouse.move(corner.x + corner.width / 2, corner.y + corner.height / 2 + 115, { steps: 10 })
  await expect(item).toHaveClass(/is-resizing/)
  await page.mouse.up()
  await expect(item).not.toHaveAttribute('aria-label', beforeResize)
  await item.focus()
  const beforeKeyboard = await item.getAttribute('aria-label')
  await page.keyboard.press('ArrowDown')
  await expect(item).not.toHaveAttribute('aria-label', beforeKeyboard)
  await page.keyboard.press('Shift+ArrowUp')
  const panels = page.locator('.hg-body > :is(.home-card, .home-hero, .home-search)')
  const panelPadding = await page.evaluate(() => getComputedStyle(document.documentElement).fontSize)
  for (const panel of await panels.all()) await expect(panel).toHaveCSS('padding', panelPadding)
  await assertFitsViewport(page)
  for (const theme of ['dark', 'light']) {
    await page.evaluate(value => document.documentElement.setAttribute('data-theme', value), theme)
    await page.screenshot({ path: testInfo.outputPath(`home-grid-${theme}.png`), fullPage: true })
  }
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect(item).toHaveCSS('transition-duration', '0s')
  await expect(item.locator('.hg-grip')).toHaveCSS('transition-duration', '0s')
})

test('catalog activity, mobile carousel and app menus stay usable', async ({ page }, testInfo) => {
  await new SetupFlow(page).complete()
  await page.goto('/#/catalog')
  await expect(page.getByRole('button', { name: 'Installation activity', exact: true })).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 850 })
  const carousel = page.locator('.catalog-feature')
  const title = carousel.locator('strong')
  const initial = await title.textContent()
  await expect(page.locator('.catalog-feature-dot:visible')).toHaveCount(0)
  await carousel.dispatchEvent('pointerdown', { pointerType: 'touch', clientX: 280, clientY: 250 })
  await carousel.dispatchEvent('pointerup', { pointerType: 'touch', clientX: 100, clientY: 255 })
  await carousel.dispatchEvent('click')
  await expect(title).not.toHaveText(initial)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: 'Previous app', exact: true }).click()
  await expect(title).toHaveText(initial)
  await page.getByRole('button', { name: 'Pause rotation', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Resume rotation', exact: true })).toHaveAttribute('aria-pressed', 'true')
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 850 })
    const more = page.getByRole('button', { name: 'More actions for Sonarr', exact: true })
    await more.click()
    const menu = page.locator('.catalog-store-app.has-open-menu .card-menu')
    await expect(menu).toBeVisible()
    const bounds = await menu.boundingBox()
    expect(bounds.x).toBeGreaterThanOrEqual(0)
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width)
    expect(bounds.y).toBeGreaterThan(-1)
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(851)
    await page.screenshot({ path: testInfo.outputPath(`catalog-menu-${width}.png`) })
    await more.press('Escape')
    await expect(menu).toHaveCount(0)
    await assertFitsViewport(page)
  }
})

test('display size previews, persists locally and preserves usable controls', async ({ page }, testInfo) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  const account = page.locator('.nav-account > summary')
  const avatar = account.locator('.user-avatar')
  await expect(avatar).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  expect((await avatar.boundingBox()).width).toBeGreaterThanOrEqual(32)
  await expect(account.locator('.nav-account-status .status-chip > span:not(.status-dot)')).toHaveCount(0)
  await flow.settings('visuals')
  const choices = page.getByRole('group', { name: 'Display size', exact: true })
  const rootSize = () => page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))
  const original = await rootSize()
  for (const [label, scale] of [['Compact · 85%', 0.85], ['Small · 90%', 0.9], ['Standard · 100%', 1], ['Large · 110%', 1.1]]) {
    await choices.getByRole('button', { name: label, exact: true }).click()
    expect(Math.abs(await rootSize() - original * scale)).toBeLessThan(0.05)
    await expect(choices.getByRole('button', { name: label, exact: true })).toHaveAttribute('aria-pressed', 'true')
    await assertFitsViewport(page)
  }
  await choices.getByRole('button', { name: 'Compact · 85%', exact: true }).click()
  await page.reload()
  await expect(choices.getByRole('button', { name: 'Compact · 85%', exact: true })).toHaveAttribute('aria-pressed', 'true')
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const view of ['home', 'catalog', 'settings/visuals']) {
      await page.goto(`/#/${view}`)
      await expect(page.locator('.nav-tabs')).toBeVisible()
      await assertFitsViewport(page)
    }
  }
  if (testInfo.project.name === 'mobile') {
    await page.goto('/#/catalog')
    const input = page.getByRole('searchbox', { name: 'Search', exact: true })
    expect(await input.evaluate(node => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(16)
    const button = page.getByRole('button', { name: 'More actions for Sonarr', exact: true })
    expect((await button.boundingBox()).height).toBeGreaterThanOrEqual(44)
  }
  await page.setViewportSize({ width: testInfo.project.name === 'mobile' ? 390 : 1440, height: 900 })
  await page.goto('/#/home')
  await page.screenshot({ path: testInfo.outputPath('display-size-compact.png'), fullPage: true })
  await flow.settings('visuals')
  await choices.getByRole('button', { name: 'Standard · 100%', exact: true }).click()
  await expect(choices.getByRole('button', { name: 'Standard · 100%', exact: true })).toHaveAttribute('aria-pressed', 'true')
})
