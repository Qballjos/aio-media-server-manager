import { test, expect } from '@playwright/test'

const password = 'FixturePassword123!'

class SetupFlow {
  constructor(page) { this.page = page }
  async complete(url = '/') {
    const page = this.page
    await page.goto(url)
    await page.getByLabel('Username', { exact: true }).fill('admin')
    await page.getByLabel('Email address', { exact: true }).fill('fixture@example.test')
    await page.getByLabel('Password (minimum 8 characters)', { exact: true }).fill(password)
    await page.getByLabel('Confirm password', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Create account', exact: true }).click()
    await expect(page.getByLabel('Media directory', { exact: true })).toBeVisible({ timeout: 30000 })
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
  await page.getByRole('button', { name: 'Request seasons', exact: true }).click()
  const requestDialog = page.getByRole('dialog', { name: 'Request Synthetic Journey' })
  const confirm = requestDialog.getByRole('button', { name: 'Request', exact: true })
  await expect(requestDialog.getByRole('checkbox', { name: 'Season 1' })).not.toBeChecked()
  await expect(confirm).toBeDisabled()
  expect((await flow.state()).requested).toBe(false)
  await requestDialog.getByRole('checkbox', { name: 'Season 2' }).check()
  await confirm.click()
  await expect.poll(async () => (await flow.state()).requested_seasons).toEqual([2])
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
  await expect.poll(async () => (await flow.state()).preferences?.quality).toBe('original')
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


test('calendar controls preserve a manually selected view across viewport changes', async ({ page }, testInfo) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  const calendar = page.locator('.home-card-calendar')
  await expect(calendar).toBeVisible()
  await calendar.getByRole('button', { name: 'Calendar view', exact: true }).click()
  await page.getByRole('option', { name: 'Month', exact: true }).click()
  await expect(calendar.locator('.cal-mode-month')).toBeVisible()
  const today = calendar.getByRole('button', { name: 'Today', exact: true })
  if (await today.isVisible()) await today.click()
  const event = calendar.getByRole('link', { name: /Calendar fixture/ })
  await event.scrollIntoViewIfNeeded()
  await expect(event.getByText('Calendar fixture', { exact: true })).toBeVisible()
  await expect(event.getByRole('img', { name: 'Series premiere' })).toBeVisible()
  const surface = calendar.getByRole('group', { name: 'Swipe or use arrow keys to change dates' })
  const heading = calendar.getByRole('heading')
  const month = await heading.innerText()
  const nextMonth = await page.evaluate(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth() + 1, 1)
      .toLocaleDateString('en', { month: 'long', year: 'numeric' })
  })
  if (testInfo.project.name === 'mobile') {
    await surface.evaluate(target => {
      const touch = clientX => new Touch({ identifier: 1, target, clientX, clientY: 80 })
      for (let i = 0; i < 2; i++) {
        target.dispatchEvent(new TouchEvent('touchstart', { touches: [touch(150)], bubbles: true }))
        target.dispatchEvent(new TouchEvent('touchend', { changedTouches: [touch(50)], bubbles: true }))
      }
    })
  } else {
    await surface.hover()
    await page.mouse.wheel(115, 0)
    await page.mouse.wheel(115, 0)
  }
  await expect(heading).toHaveText(nextMonth)
  const incoming = calendar.locator('.cal-mode-month.cal-slide-next')
  await expect(incoming).toBeVisible()
  await expect(incoming).toHaveCSS('animation-duration', '0.24s')
  await expect(surface).toHaveCSS('scrollbar-width', 'none')
  await today.click()
  await expect(calendar.getByRole('heading')).toHaveText(month)
  const viewport = page.viewportSize()
  await page.setViewportSize({ width: viewport.width < 600 ? 1100 : 390, height: viewport.height })
  await expect(calendar.locator('.cal-mode-month')).toBeVisible()
  await page.setViewportSize(viewport)
  await assertFitsViewport(page)
})


test('trending requests are only available in the poster dialog', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/trending')
  await page.reload()
  const tile = page.locator('.home-tile-trending').filter({ hasText: 'Trending Fixture' })
  await expect(tile).toBeVisible()
  await expect(tile.getByText('2026', { exact: true })).toHaveCount(0)
  const rail = tile.locator('..')
  await expect(rail).toHaveAttribute('tabindex', '0')
  await expect(page.getByRole('button', { name: /^(Previous|Next) trending$/ })).toHaveCount(0)
  await expect(tile.locator('.home-tile-request')).toHaveCount(0)
  await tile.locator('.home-tile-link').click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Trending Fixture', exact: true })).toBeVisible()
  await expect(dialog.getByText('2026', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Request', exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Open in Seerr', exact: true })).toHaveCount(0)
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
  await page.getByRole('dialog', { name: 'Request Trending Fixture' })
    .getByRole('button', { name: 'Request', exact: true }).click()
  await expect.poll(async () => (await flow.state()).requested).toBe(true)
})

test('trending hides existing and deleted titles by default', async ({ page }) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/trending-statuses')
  await page.reload()
  const trending = page.locator('.home-card-trending')
  await expect(trending.locator('.home-tile-trending')).toHaveCount(1)
  await expect(trending.getByText('Missing Trending', { exact: true })).toBeVisible()
  await expect(trending.getByRole('switch')).toHaveCount(0)
  await trending.getByRole('button', { name: 'Series', exact: true }).click()
  await expect(trending.locator('.home-tile-trending')).toHaveCount(0)
  await trending.getByRole('button', { name: 'All', exact: true }).click()
  await expect(trending.locator('.home-tile-trending')).toHaveCount(1)
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

test('two-factor authentication setup and recovery login', async ({ page }) => {
  const { createHmac } = await import('node:crypto')
  const flow = new SetupFlow(page)
  await flow.complete()
  await flow.settings('account')

  const card = page.getByRole('heading', { name: 'Two-factor authentication', exact: true }).locator('../..')
  await card.getByLabel('Current password', { exact: true }).fill(password)
  await card.getByRole('button', { name: 'Set up authenticator' }).click()
  const qr = card.getByRole('img', { name: 'Authenticator setup QR code' })
  await expect(qr).toBeVisible()
  await expect.poll(() => qr.evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true)
  await assertFitsViewport(page)

  const secret = await card.getByLabel('Setup key').inputValue()
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  const bits = [...secret].map(char => alphabet.indexOf(char).toString(2).padStart(5, '0')).join('')
  const key = Buffer.from(bits.match(/.{8}/g).map(byte => Number.parseInt(byte, 2)))
  const message = Buffer.alloc(8)
  message.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)))
  const digest = createHmac('sha1', key).update(message).digest()
  const code = ((digest.readUInt32BE(digest.at(-1) & 15) & 0x7fffffff) % 1000000).toString().padStart(6, '0')
  await card.getByLabel('Authenticator code', { exact: true }).fill(code)
  let releaseEnable
  const waitToEnable = new Promise(resolve => { releaseEnable = resolve })
  await page.route('**/api/auth/two-factor/enable', async route => {
    await waitToEnable
    await route.continue()
  })
  const response = page.waitForResponse('**/api/auth/two-factor/enable')
  await card.getByRole('button', { name: 'Enable two-factor authentication' }).click()
  await flow.settings('system')
  await expect(card).toHaveCount(0)
  releaseEnable()
  expect((await response).ok()).toBe(true)
  await flow.settings('account')
  const recovery = card.getByLabel('Recovery codes', { exact: true })
  await expect(recovery).toBeVisible()
  const [recoveryCode] = (await recovery.inputValue()).split('\n')
  await assertFitsViewport(page)
  await card.getByRole('button', { name: 'I saved my recovery codes' }).click()
  await expect(recovery).toHaveCount(0)

  await page.evaluate(async () => {
    const token = localStorage.getItem('amm_token')
    await fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    localStorage.removeItem('amm_token')
    sessionStorage.removeItem('amm_csrf')
  })
  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  const factor = page.getByLabel('Authenticator or recovery code')
  await expect(factor).toBeFocused()
  await assertFitsViewport(page)
  await factor.fill('0000000000')
  await page.getByRole('button', { name: 'Verify and sign in' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Invalid or already used verification code.' })).toBeVisible()
  await factor.fill(recoveryCode)
  await page.getByRole('button', { name: 'Verify and sign in' }).click()
  await expect(page.getByRole('searchbox', { name: 'Search', exact: true })).toBeVisible({ timeout: 30000 })
})

test('passkey registration, sign-in, and removal', async ({ page, context, baseURL }) => {
  const url = new URL(baseURL)
  url.hostname = 'localhost'
  await page.route('**/*', route => new URL(route.request().url()).origin === url.origin ? route.continue() : route.abort())
  await page.goto(url.origin)
  const cdp = await context.newCDPSession(page)
  await cdp.send('WebAuthn.enable')
  await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2', transport: 'internal', hasResidentKey: true,
      hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true,
    },
  })

  const flow = new SetupFlow(page)
  await flow.complete(url.origin)
  await page.evaluate(() => { location.hash = '/settings/account' })
  const card = page.getByRole('heading', { name: 'Passkey', exact: true }).locator('../..')
  await card.getByLabel('Current password', { exact: true }).fill(password)
  await card.getByRole('button', { name: 'Add passkey', exact: true }).click()
  await expect(card.getByText(/A passkey is registered/)).toBeVisible()
  await assertFitsViewport(page)

  await page.evaluate(async () => {
    const token = localStorage.getItem('amm_token')
    await fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    localStorage.removeItem('amm_token')
    sessionStorage.removeItem('amm_csrf')
  })
  await page.goto(url.origin)
  await page.getByRole('button', { name: 'Sign in with a passkey', exact: true }).click()
  await expect(page.getByRole('searchbox', { name: 'Search', exact: true })).toBeVisible({ timeout: 30000 })

  await page.evaluate(() => { location.hash = '/settings/account' })
  await card.getByLabel('Current password', { exact: true }).fill(password)
  await card.getByRole('button', { name: 'Remove passkey', exact: true }).click()
  await expect(card.getByRole('button', { name: 'Add passkey', exact: true })).toBeVisible()
})

test.describe('media-account login', () => {
  test.use({ serviceWorkers: 'block' })

  for (const provider of ['jellyfin', 'plex']) {
    test(`media sign-in with ${provider} stays in the limited dashboard`, async ({ page }) => {
      let signedIn = false
      let approvals = 0
      let requestSent = false
      let displayName = ''
      let avatarUrl = null
      const avatarPath = '/api/media-discovery/profile/avatar'
      const avatar = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf2sAAAAASUVORK5CYII=', 'base64')
      const paged = (page, first, last, extra) => ({
        items: page === '2' ? [last] : [first, ...Array.from({ length: 15 }, (_, index) => extra(index))],
        has_more: page === '1',
      })
      const adminRequests = []
      const fixturePoster = '/poster-fixture/catalog.png'
      await page.route('**/poster-fixture/catalog.png', route => route.fulfill({ contentType: 'image/png', body: avatar }))
      // Exercise browsers that give an image no layout box until a source is assigned.
      await page.addInitScript(() => {
        document.addEventListener('DOMContentLoaded', () => {
          const style = document.createElement('style')
          style.textContent = '.home-tile-poster:not([src]) { display: none }'
          document.head.append(style)
        })
      })
      await page.route('**/api/**', async route => {
        const url = new URL(route.request().url())
        const path = url.pathname
        const pageNumber = url.searchParams.get('page')
        if (path === '/api/auth/status') return route.fulfill({ json: { authenticated: false, setup_required: false } })
        if (path === '/api/media-login/options') return route.fulfill({ json: { provider } })
        if (path === avatarPath) {
          if (route.request().method() === 'GET') return route.fulfill({ contentType: 'image/png', body: avatar })
          if (route.request().method() === 'PUT') {
            expect(route.request().postDataBuffer()).toEqual(avatar)
            avatarUrl = `${avatarPath}?v=fixture`
          } else {
            avatarUrl = null
          }
          return route.fulfill({ json: { avatar_url: avatarUrl } })
        }
        if (path === '/api/media-discovery/profile') {
          if (route.request().method() === 'PATCH') {
            displayName = route.request().postDataJSON().display_name
          }
          return route.fulfill({ json: { username: 'media-viewer', display_name: displayName, avatar_url: avatarUrl } })
        }
        if (path === '/api/media-discovery/quota') {
          return route.fulfill({ json: { movie: { limit: 5, remaining: 0, days: 7 }, tv: null } })
        }
        if (path === '/api/support' && route.request().method() === 'POST') {
          const payload = route.request().postDataJSON()
          if (payload.subject === 'Shared library title') {
            expect(payload).toEqual({ subject: 'Shared library title', message: 'Subtitles missing.' })
          } else {
            expect(payload).toEqual({ subject: 'Trending title', message: 'Request #2\n\nWrong season.' })
          }
          return route.fulfill({ status: 201, json: { id: 'report-1' } })
        }
        if (path === '/api/support') return route.fulfill({ json: { reports: [{ status: 'in_progress' }], new_count: 0 } })
        if (path === '/api/media-discovery/tv/5/seasons') return route.fulfill({ json: { seasons: [2] } })
        if (path === '/api/media-discovery/requests' && route.request().method() === 'POST') {
          expect(route.request().postDataJSON()).toEqual({ mediaType: 'tv', mediaId: 5, seasons: [2] })
          requestSent = true
          return route.fulfill({ status: 201, json: { id: 2 } })
        }
        if (path === '/api/media-discovery/requests') {
          const item = requestSent
            ? { id: 2, title: 'Trending title', status: 'pending', mediaType: 'tv', seasons: [2], createdAt: '2026-11-18T12:00:00Z' }
            : { id: 1, title: 'My requested film', status: 'approved', poster: fixturePoster }
          return route.fulfill({ json: requestSent ? { items: [item], has_more: false } : paged(
            pageNumber, item, { id: 90, title: 'Older request', status: 'approved' },
            index => ({ id: 100 + index, title: `Request filler ${index}`, status: 'approved' }),
          ) })
        }
        if (path.startsWith('/api/media-discovery/recent/art/')) {
          return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="30"/>' })
        }
        if (path === '/api/media-discovery/recent') {
          return route.fulfill({ json: paged(pageNumber, {
            id: 'shared-3', title: 'Shared library title', mediaType: 'tv', overview: 'A shared series.',
            playProvider: provider, playUrl: `https://${provider}.example.test/web/#/details?id=shared-3`,
          }, { id: 'older-31', title: 'Older library title', mediaType: 'movie' },
          index => ({ id: `recent-filler-${index}`, title: `Recent filler ${index}`, mediaType: 'movie' })) })
        }
        if (path === '/api/media-discovery/resume') {
          return route.fulfill({ json: { items: [{
            id: 'resume-1', posterId: 'shared-3', title: 'In progress series', mediaType: 'tv', detail: 'Episode 2',
            playUrl: `https://${provider}.example.test/web/#/details?id=resume-1`,
          }] } })
        }
        if (path === '/api/media-discovery/calendar') {
          const params = new URL(route.request().url()).searchParams
          const start = params.get('start')
          expect(start).toMatch(/^\d{4}-\d{2}-\d{2}$/)
          if (params.has('own_requests')) return route.fulfill({ json: { items: [{
            kind: 'movie', title: 'My future film', when: `${start}T12:00:00`, available: false,
          }] } })
          return route.fulfill({ json: { items: [{
            kind: 'movie', title: 'Shared future film', detail: '2026', when: `${start}T12:00:00`, available: false,
          }, {
            kind: 'episode', title: 'Shared season', detail: 'S02E08', when: `${start}T12:00:00`,
            available: false, milestones: ['season-finale'],
          }] } })
        }
        if (path === '/api/media-discovery/titles/tv/5') {
          return route.fulfill({ json: {
            title: 'Trending title', overview: 'The trending series synopsis.',
            poster: '/api/media-discovery/recent/art/shared-3',
            trailer: 'https://www.youtube.com/watch?v=abcdefghijk', voteAverage: 8.5,
            streaming: { configured: true, providers: [{ id: 8, name: 'Netflix', logo_url: fixturePoster }], link: '' },
          } })
        }
        if (path === '/api/media-discovery/trending') {
          const items = requestSent ? [] : [{
            mediaType: 'tv', mediaId: 5, title: 'Trending title', poster: fixturePoster, availableSeasons: [1], requestableSeasons: [2],
          }]
          return route.fulfill({ json: requestSent ? { items, has_more: false } : paged(
            pageNumber, items[0], { mediaType: 'movie', mediaId: 99, title: 'More trending' },
            index => ({ mediaType: 'movie', mediaId: 100 + index, title: `Trending filler ${index}` }),
          ) })
        }
        if (path === '/api/media-discovery/search') {
          expect(new URL(route.request().url()).searchParams.get('q')).toBe('Test film')
          return route.fulfill({ json: { items: [
            { mediaType: 'movie', mediaId: 4, title: 'Test film', available: true, poster: fixturePoster },
            { mediaType: 'tv', mediaId: 5, title: 'Trending title', requestableSeasons: [2] },
          ] } })
        }
        if (path === '/api/media-login/session') {
          return route.fulfill({ status: signedIn ? 200 : 401, json: signedIn ? { account_id: '42' } : {} })
        }
        if (path === `/api/media-login/${provider}`) {
          const prompt = provider === 'plex' ? { authorize_url: 'https://app.plex.tv/auth' } : { code: '123456' }
          return route.fulfill({ json: { attempt: 'fixture-attempt', ...prompt } })
        }
        if (path === `/api/media-login/${provider}/complete`) {
          expect(route.request().headers()['x-aio-media-attempt']).toBe('fixture-attempt')
          if (!approvals++) return route.fulfill({ status: 202, json: { status: 'pending' } })
          signedIn = true
          return route.fulfill({ json: { account_id: '42' } })
        }
        if (path === '/api/media-login/logout') {
          signedIn = false
          return route.fulfill({ status: 204 })
        }
        if (/^\/api\/(catalog|applications|system|wizard|settings)/.test(path)) adminRequests.push(path)
        return route.fulfill({ json: {} })
      })

      await page.goto('/#/catalog')
      await page.getByRole('button', { name: new RegExp(`Sign in with ${provider}`, 'i') }).click()
      if (provider === 'plex') {
        await expect(page.getByRole('link', { name: 'Open Plex to approve' })).toHaveAttribute('href', 'https://app.plex.tv/auth')
      } else {
        await expect(page.getByText('123456', { exact: true })).toBeVisible()
      }
      await assertFitsViewport(page)
      await page.getByRole('button', { name: 'Check approval' }).click()
      await expect(page.getByText('Approval is still pending.')).toBeVisible()
      await page.getByRole('button', { name: 'Check approval' }).click()
      await expect(page).toHaveURL(/#\/home$/)
      const greeting = page.getByRole('region', { name: 'Greeting' })
      await expect(greeting.getByRole('heading')).toHaveText(/Good (night|morning|afternoon|evening)/)
      const searchWidget = page.getByRole('region', { name: 'Search', exact: true })
      await expect(greeting).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
      await expect(searchWidget).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
      await expect(searchWidget.getByRole('button', { name: 'Search in' })).toHaveCount(0)
      await expect(page.getByText('Trending title', { exact: true })).toBeVisible()
      for (const [railName, secondPageTitle] of [
        ['Trending', 'More trending'], ['My requests', 'Older request'], ['Newly available', 'Older library title'],
      ]) {
        const widget = page.getByRole('region', { name: railName, exact: true })
        const rail = widget.locator('.home-rail')
        await expect(widget.getByRole('button', { name: /^(Previous|Next|Refresh|Load more)$/ })).toHaveCount(0)
        await expect(rail).toHaveCSS('scrollbar-width', 'none')
        await expect(rail.getByText(secondPageTitle, { exact: true })).toHaveCount(0)
        await rail.scrollIntoViewIfNeeded()
        const firstPoster = rail.locator('img').first()
        await expect.poll(() => firstPoster.evaluate(img => img.naturalWidth)).toBeGreaterThan(0)
        await rail.press('ArrowRight')
        await expect.poll(() => rail.evaluate(node => node.scrollLeft)).toBeGreaterThan(0)
        await rail.evaluate(node => { node.scrollLeft = node.scrollWidth })
        await expect(rail.getByText(secondPageTitle, { exact: true })).toHaveCount(1)
        await expect(widget.getByRole('button', { name: 'Load more' })).toHaveCount(0)
        if (railName === 'Newly available') {
          await rail.evaluate(node => { node.scrollLeft = node.scrollWidth })
          const poster = rail.getByRole('button', { name: secondPageTitle, exact: true }).locator('img')
          await expect.poll(() => poster.evaluate(img => img.naturalWidth)).toBeGreaterThan(0)
        }
        await rail.evaluate(node => { node.scrollLeft = 0 })
      }
      const calendar = page.getByRole('region', { name: 'Calendar', exact: true })
      await calendar.getByRole('button', { name: 'Calendar view' }).click()
      const monthResponse = page.waitForResponse(response => {
        const params = new URL(response.url()).searchParams
        return response.url().includes('/api/media-discovery/calendar?') && Number(params.get('days')) >= 28
      })
      await page.getByRole('option', { name: 'Month' }).click()
      await monthResponse
      await expect(calendar.locator('.cal-mode-month .cal-day')).not.toHaveCount(0)
      await calendar.getByRole('button', { name: 'Calendar view' }).click()
      await page.getByRole('option', { name: 'Day', exact: true }).click()
      await expect(calendar.getByText('Shared future film')).toBeVisible()
      await expect(calendar.getByRole('img', { name: 'Season finale' })).toBeVisible()
      await expect(calendar.getByText('Upcoming', { exact: true }).first()).toBeVisible()
      const surface = calendar.getByRole('group', { name: 'Swipe or use arrow keys to change dates' })
      const dateHeading = await calendar.getByRole('heading').innerText()
      await surface.press('ArrowRight')
      await expect(calendar.getByRole('heading')).not.toHaveText(dateHeading)
      // The next day can already be in the range cache.
      await expect(calendar.getByText('Shared future film')).toBeVisible()
      await calendar.getByRole('button', { name: 'Calendar releases' }).click()
      await page.getByRole('option', { name: 'My requests', exact: true }).click()
      await expect(calendar.getByText('My future film')).toBeVisible()
      await expect(calendar.getByText('Shared future film')).toHaveCount(0)

      const editHome = page.getByRole('button', { name: 'Edit the Home layout' })
      await editHome.click()
      await page.getByRole('button', { name: 'Continue watching', exact: true }).click()
      const resume = page.getByRole('region', { name: 'Continue watching', exact: true })
      await expect(resume.getByRole('link', { name: 'Open In progress series to continue watching' }))
        .toHaveAttribute('href', `https://${provider}.example.test/web/#/details?id=resume-1`)
      await page.getByRole('button', { name: 'Done arranging Home', exact: true }).click()
      await expect(page.getByRole('region', { name: 'Trending', exact: true }).getByText('Partially available')).toBeVisible()
      const recentTile = page.getByRole('region', { name: 'Newly available' }).getByRole('button', { name: /Shared library title/ })
      await recentTile.scrollIntoViewIfNeeded()
      await expect.poll(() => recentTile.locator('img').evaluate(img => img.naturalWidth)).toBeGreaterThan(0)
      await recentTile.locator('img').click()
      const titleDetails = page.getByRole('dialog', { name: 'Title details' })
      await expect(titleDetails.getByText('A shared series.')).toBeVisible()
      const bounds = await titleDetails.boundingBox()
      const viewport = page.viewportSize()
      expect(Math.abs(bounds.x + bounds.width / 2 - viewport.width / 2)).toBeLessThan(3)
      expect(Math.abs(bounds.y + bounds.height / 2 - viewport.height / 2)).toBeLessThan(3)
      await expect(titleDetails.getByRole('link', { name: `Open in ${provider === 'plex' ? 'Plex' : 'Jellyfin'}` }))
        .toHaveAttribute('href', `https://${provider}.example.test/web/#/details?id=shared-3`)
      await titleDetails.getByLabel('Description', { exact: true }).fill('Subtitles missing.')
      await titleDetails.getByRole('button', { name: 'Send report' }).click()
      await expect(titleDetails.getByText('Report sent to the administrator.')).toBeVisible()
      await titleDetails.getByRole('button', { name: 'Close', exact: true }).click()
      const ownRequests = page.getByRole('region', { name: 'My requests' })
      await expect(ownRequests.getByText('My requested film')).toBeVisible()
      await expect(ownRequests.getByRole('button', { name: 'Open request details for My requested film' })
        .getByText('Approved', { exact: true })).toBeVisible()
      const limits = page.getByRole('region', { name: 'Request limits' })
      await expect(limits.getByText('0 of 5 remaining per 7 days')).toBeVisible()
      await expect(limits.getByText('No limit', { exact: true })).toBeVisible()
      await expect(page.getByText('Open reports: 1')).toBeVisible()
      const support = page.getByRole('region', { name: 'Support', exact: true })
      const supportLink = support.getByRole('link', { name: 'Open support' })
      await expect(supportLink).toHaveAttribute('href', '#/settings/support')
      const supportTextBox = await support.getByText('Open reports: 1').boundingBox()
      const supportLinkBox = await supportLink.boundingBox()
      expect(supportLinkBox.y - (supportTextBox.y + supportTextBox.height)).toBeGreaterThanOrEqual(12)
      await page.getByRole('searchbox', { name: 'Search films and series' }).fill('Test film')
      await page.getByRole('button', { name: 'Search', exact: true }).click()
      await expect(page.getByText('Test film', { exact: true })).toBeVisible()
      const searchResults = page.getByRole('region', { name: 'Search', exact: true })
      await expect(searchResults.getByText('Available', { exact: true })).toBeVisible()
      await expect.poll(() => searchResults.locator('img').evaluate(img => img.naturalWidth)).toBeGreaterThan(0)
      await searchResults.getByRole('button', { name: 'Request seasons' }).click()
      const searchRequest = page.getByRole('dialog', { name: 'Request media' })
      await expect(searchRequest.getByRole('checkbox', { name: 'Season 2' })).toBeVisible()
      await expect(searchRequest.getByRole('checkbox', { name: 'Season 1' })).toHaveCount(0)
      await expect(searchRequest.getByRole('button', { name: 'Send request' })).toBeDisabled()
      await searchRequest.getByRole('button', { name: 'Cancel' }).click()
      await searchResults.getByRole('button', { name: 'Close' }).click()
      const trendingTile = page.getByRole('region', { name: 'Trending', exact: true })
      await expect(trendingTile.getByRole('button', { name: /Request Trending title/ })).toHaveCount(0)
      await trendingTile.getByRole('button', { name: 'Trending title', exact: true }).click()
      const trendingDetails = page.getByRole('dialog', { name: 'Title details' })
      await expect(trendingDetails.getByText('The trending series synopsis.')).toBeVisible()
      await expect(trendingDetails.locator('.home-title-poster')).toBeVisible()
      await expect(trendingDetails.getByText('8.5')).toBeVisible()
      const streaming = trendingDetails.getByRole('region', { name: 'Streaming availability' })
      await expect(streaming).toContainText('Netflix')
      await expect.poll(() => streaming.locator('img').evaluate(image => image.naturalWidth)).toBeGreaterThan(0)
      await expect(streaming).toContainText('Season availability may vary.')
      await trendingDetails.getByRole('button', { name: 'Trailer', exact: true }).click()
      await expect(trendingDetails.locator('iframe')).toHaveAttribute('src', /youtube-nocookie\.com\/embed\/abcdefghijk/)
      await trendingDetails.getByRole('button', { name: 'Request remaining seasons', exact: true }).click()
      const requestDialog = page.getByRole('dialog', { name: 'Request media' })
      await expect(requestDialog.getByRole('checkbox', { name: 'Season 1' })).toHaveCount(0)
      await requestDialog.getByRole('checkbox', { name: 'Season 2' }).check()
      await requestDialog.getByRole('button', { name: 'Send request' }).click()
      await expect(ownRequests.getByText('Waiting for approval')).toBeVisible()
      await expect(trendingTile.getByRole('button', { name: 'Trending title', exact: true })).toHaveCount(0)
      await ownRequests.getByRole('button', { name: 'Open request details for Trending title' }).click()
      const details = page.getByRole('dialog', { name: 'Request details' })
      await expect(details.getByText('Waiting for approval')).toBeVisible()
      await expect(details.getByText('Season 2', { exact: true })).toBeVisible()
      await expect(details.getByText('Requested on', { exact: true })).toBeVisible()
      await assertFitsViewport(page)
      await details.getByLabel('Description', { exact: true }).fill('Wrong season.')
      await details.getByRole('button', { name: 'Send report', exact: true }).click()
      await expect(details.getByText('Report sent to the administrator.')).toBeVisible()
      await details.getByRole('button', { name: 'Close', exact: true }).click()
      await assertFitsViewport(page)
      await expect(page.getByRole('link', { name: 'Catalog' })).toHaveCount(0)
      const edit = page.getByRole('button', { name: 'Edit the Home layout' })
      await edit.click()
      await page.getByRole('button', { name: 'Remove Trending' }).click()
      await expect(page.getByRole('region', { name: 'Trending' })).toHaveCount(0)
      await page.getByRole('button', { name: 'Trending', exact: true }).click()
      await page.getByRole('button', { name: 'Done arranging Home' }).click()
      await expect(page.getByRole('region', { name: 'Trending' })).toBeVisible()
      await page.getByRole('link', { name: 'Settings', exact: true }).click()
      await expect(page.getByLabel('Username', { exact: true })).toHaveValue('media-viewer')
      await page.getByLabel('Display name').fill('Sam')
      await page.getByRole('button', { name: 'Save profile' }).click()
      await expect(page.getByText('Account updated.')).toBeVisible()
      await page.getByLabel('Upload profile image').setInputFiles({ name: 'avatar.png', mimeType: 'image/png', buffer: avatar })
      await expect(page.getByText('Profile image updated.')).toBeVisible()
      const topAvatar = page.locator('.nav-account .user-avatar-img')
      await expect(topAvatar).toHaveAttribute('src', `${avatarPath}?v=fixture`)
      await page.reload()
      await expect(page.getByLabel('Display name')).toHaveValue('Sam')
      await expect.poll(() => topAvatar.evaluate(img => img.naturalWidth)).toBeGreaterThan(0)
      await page.getByRole('button', { name: 'Remove', exact: true }).click()
      await expect(page.getByText('Profile image removed.')).toBeVisible()
      await expect(topAvatar).toHaveCount(0)
      await assertFitsViewport(page)
      const picker = page.locator('#settings-section-select')
      if (await picker.isVisible()) {
        await picker.click()
        await page.getByRole('option', { name: 'Language and appearance' }).click()
      } else {
        await page.getByRole('link', { name: 'Language and appearance' }).click()
      }
      await expect(page.getByRole('group', { name: 'Themes', exact: true })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Brand name and icons' })).toHaveCount(0)
      await page.getByRole('button', { name: 'Light', exact: true }).click()
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
      await page.reload()
      await expect(page.getByRole('group', { name: 'Themes', exact: true })).toBeVisible()
      await expect(page.getByRole('link', { name: 'Catalog' })).toHaveCount(0)
      expect(adminRequests).toEqual([])
    })
  }
})

test.describe('media user administration', () => {
  test.use({ serviceWorkers: 'block' })

  test('grants and revokes media access', async ({ page }) => {
    await page.route('**/api/**', async route => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path === '/api/auth/status') return route.fulfill({ json: { authenticated: true, username: 'admin' } })
      if (path === '/api/wizard/status') return route.fulfill({ json: { completed: true } })
      if (path === '/api/settings/media-users' && request.method() === 'GET') {
        return route.fulfill({ json: { provider: 'jellyfin', users: [{ id: '42', name: 'Viewer', imported: false, enabled: false }] } })
      }
      if (path === '/api/settings/media-users' && request.method() === 'POST') {
        expect(request.postDataJSON()).toEqual({ account_ids: ['42'] })
        return route.fulfill({ json: { enabled: ['42'] } })
      }
      if (path === '/api/settings/media-users/42' && request.method() === 'DELETE') return route.fulfill({ status: 204 })
      return route.fulfill({ json: {} })
    })

    await page.goto('/#/settings/users')
    await expect(page.getByRole('heading', { name: 'Jellyfin accounts' })).toBeVisible()
    await assertFitsViewport(page)
    await page.getByRole('checkbox', { name: 'Viewer' }).check()
    await page.getByRole('button', { name: 'Grant access', exact: true }).click()
    await expect(page.getByText('AIO access enabled', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Revoke access for Viewer' }).click()
    await expect(page.getByText('Imported in Seerr', { exact: true })).toBeVisible()
    await expect(page.getByRole('status').filter({ hasText: 'Access revoked for Viewer.' })).toBeVisible()
  })
})

test.describe('support settings', () => {
  test.use({ serviceWorkers: 'block' })

  test('delivers a member report and shows the administrator reply', async ({ page }) => {
    let admin = false
    let report
    await page.route('**/api/**', async route => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path === '/api/auth/status') return route.fulfill({ json: { authenticated: admin, username: admin ? 'admin' : null } })
      if (path === '/api/wizard/status') return route.fulfill({ json: { completed: true } })
      if (path === '/api/media-login/session') return route.fulfill({ json: { account_id: '42' } })
      if (path === '/api/support' && request.method() === 'POST') {
        expect(request.postDataJSON()).toEqual({ subject: 'Playback', message: 'Audio stops.' })
        report = {
          ...request.postDataJSON(), id: 'report-1', status: 'new', replies: [],
          provider: 'jellyfin', account_id: '42', created_at: '2026-11-18 12:00:00',
        }
        return route.fulfill({ status: 201, json: report })
      }
      if (path === '/api/support') {
        return route.fulfill({ json: { reports: report ? [report] : [], new_count: admin && report?.status === 'new' ? 1 : 0 } })
      }
      if (path === '/api/support/report-1/replies') {
        report.replies.push({ id: 1, author: 'admin', message: request.postDataJSON().message, created_at: report.created_at })
        return route.fulfill({ status: 201, json: report })
      }
      if (path === '/api/support/report-1') {
        if (request.method() === 'PATCH') report.status = request.postDataJSON().status
        return route.fulfill({ json: report })
      }
      return route.fulfill({ json: {} })
    })

    await page.goto('/#/settings/account')
    const picker = page.locator('#settings-section-select')
    if (await picker.isVisible()) {
      await picker.click()
      await page.getByRole('option', { name: 'Support', exact: true }).click()
    } else {
      await page.getByRole('link', { name: 'Support', exact: true }).click()
    }
    await page.getByLabel('Subject', { exact: true }).fill('Playback')
    await page.getByLabel('Description', { exact: true }).fill('Audio stops.')
    await page.getByRole('button', { name: 'Send report' }).click()
    await expect(page.getByText('Audio stops.')).toBeVisible()
    await assertFitsViewport(page)

    admin = true
    await page.reload()
    await expect(page.getByText('New reports: 1')).toBeVisible()
    await page.getByRole('button', { name: 'Playback', exact: true }).click()
    await page.getByLabel('Reply', { exact: true }).fill('Please retry.')
    await page.getByRole('button', { name: 'Send reply' }).click()
    await expect(page.getByText('Please retry.')).toBeVisible()
    await page.getByRole('button', { name: 'Resolved', exact: true }).click()
    await expect(page.getByText('New reports: 0')).toBeVisible()
    await assertFitsViewport(page)

    admin = false
    await page.reload()
    await page.getByRole('button', { name: 'Playback', exact: true }).click()
    await expect(page.getByText('Please retry.')).toBeVisible()
  })
})

test.describe('request review', () => {
  test.use({ serviceWorkers: 'block' })

  test('administrator approves and declines pending requests from Home', async ({ page }) => {
    const decisions = new Map()
    let otherItems = []
    await page.clock.install()
    const downloadItems = [
      { title: 'Healthy transfer', source: 'qbittorrent', status: 'Downloading', progress: 40 },
      { title: 'Problem transfer', source: 'qbittorrent', status: 'Stalled', progress: 25 },
    ]
    await page.route('**/api/**', async route => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path === '/api/auth/status') return route.fulfill({ json: { authenticated: true, username: 'admin' } })
      if (path === '/api/wizard/status') return route.fulfill({ json: { completed: true } })
      if (path === '/api/homepage/other-downloads') return route.fulfill({ json: { items: otherItems } })
      if (path === '/api/homepage/downloads') return route.fulfill({ json: { downloads: downloadItems } })
      if (path === '/api/homepage') {
        const requests = [4, 5, 6].map(id => ({
          requestId: id, requestStatus: id === 6 ? 2 : decisions.get(id) || 1, mediaType: 'movie', mediaId: id,
          title: `Fixture Film ${id}`, detail: 'Viewer', status: id === 6 ? 'available' : 'requested',
        }))
        return route.fulfill({ json: { apps: [{ name: 'seerr', display_name: 'Seerr' }], requests, downloads: downloadItems, seerr: { available: true } } })
      }
      const match = path.match(/^\/api\/homepage\/requests\/(\d+)\/(approve|decline)$/)
      if (match) {
        expect(request.method()).toBe('POST')
        decisions.set(Number(match[1]), match[2] === 'approve' ? 2 : 3)
        return route.fulfill({ json: { ok: true } })
      }
      return route.fulfill({ json: {} })
    })

    await page.goto('/#/home')
    const dialog = page.getByRole('dialog', { name: 'Review request' })
    await page.getByRole('button', { name: 'Edit the Home layout' }).click()
    await page.getByRole('button', { name: 'Add widget', exact: true }).click()
    await page.getByRole('dialog', { name: 'Add widget' }).getByRole('button', { name: /^Pending requests/ }).click()
    await page.getByRole('button', { name: 'Add widget', exact: true }).click()
    await page.getByRole('dialog', { name: 'Add widget' }).getByRole('button', { name: /^Other downloads/ }).click()
    const other = page.locator('[data-widget="other"]')
    await expect(other.getByText('Nothing besides films and series.')).toBeVisible()
    await page.getByRole('button', { name: 'Done', exact: true }).click()
    await expect(other).toHaveCount(0)
    const approvals = page.getByRole('region', { name: 'Pending requests' })
    await approvals.getByRole('button', { name: 'Review request · Fixture Film 4' }).click()
    await expect(dialog.getByText('Requested by Viewer')).toBeVisible()
    await assertFitsViewport(page)
    await dialog.getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(page.getByText('Request approved.', { exact: true })).toBeVisible()
    await expect(approvals.getByText('Fixture Film 4')).toHaveCount(0)
    await approvals.getByRole('button', { name: 'Review request · Fixture Film 5' }).click()
    await dialog.getByRole('button', { name: 'Decline', exact: true }).click()
    await expect(page.getByText('Request declined.', { exact: true })).toBeVisible()
    await expect(approvals).toHaveCount(0)
    await page.getByRole('button', { name: 'Filter request availability' }).click()
    await page.getByRole('option', { name: 'Approved, awaiting availability' }).click()
    const requests = page.locator('[data-widget="requests"]')
    await expect(requests.getByText('Fixture Film 4')).toBeVisible()
    await expect(requests.getByText('Fixture Film 5')).toHaveCount(0)
    await expect(requests.getByText('Fixture Film 6')).toHaveCount(0)
    const downloads = page.locator('.home-card-downloads')
    await expect(downloads.getByText('Problem transfer')).toBeVisible()
    await downloads.getByRole('button', { name: 'Filter downloads' }).click()
    await page.getByRole('option', { name: 'Problems', exact: true }).click()
    await expect(downloads.getByText('Problem transfer')).toBeVisible()
    await expect(downloads.getByText('Healthy transfer')).toHaveCount(0)
    expect([...decisions]).toEqual([[4, 2], [5, 3]])

    otherItems = [{ id: 'book-1', title: 'Fixture audiobook', source: 'qbittorrent', kind: 'book', done: true }]
    await page.clock.fastForward(60000)
    await expect(other.getByText('Fixture audiobook')).toBeVisible()
    otherItems = []
    await page.clock.fastForward(60000)
    await expect(other).toHaveCount(0)
  })
})

test('regional streaming subscriptions reach the Trending popup', async ({ page }, testInfo) => {
  const flow = new SetupFlow(page)
  await flow.complete()
  await page.request.post('/_test/trending')
  async function openTrending() {
    await page.locator('.home-tile-trending').filter({ hasText: 'Trending Fixture' }).locator('.home-tile-link').click()
    return page.getByRole('dialog')
  }

  await page.reload()
  const initialDialog = await openTrending()
  await initialDialog.getByRole('link', { name: 'Set up streaming subscriptions' }).click()
  const settings = page.getByRole('region', { name: 'Streaming subscriptions' })
  await expect(settings.getByRole('button', { name: 'Streaming country' })).toHaveText('Netherlands')
  await settings.getByRole('searchbox').fill('video')
  await expect(settings.getByRole('checkbox', { name: 'Netflix' })).toHaveCount(0)
  await settings.getByRole('checkbox', { name: 'Videoland' }).check()
  await settings.getByRole('button', { name: 'Save subscriptions' }).click()
  await expect(settings.getByRole('status')).toHaveText('Subscriptions saved.')
  await page.reload()
  await expect(settings.getByRole('checkbox', { name: 'Videoland' })).toBeChecked()
  await assertFitsViewport(page)
  await settings.screenshot({ path: testInfo.outputPath('streaming-settings.png') })

  await page.goto('/#/home')
  const dialog = await openTrending()
  await expect(dialog.getByRole('region', { name: 'Streaming availability' })).toContainText('Videoland')
  await expect(dialog.getByRole('link', { name: 'Where to watch' })).toHaveAttribute('href', /locale=NL$/)
  await expect(dialog.getByRole('button', { name: 'Request', exact: true })).toBeVisible()
  await assertFitsViewport(page)
  await dialog.screenshot({ path: testInfo.outputPath('streaming-popup.png') })

  await flow.settings('account')
  await settings.getByRole('button', { name: 'Streaming country' }).click()
  await page.getByRole('option', { name: 'United States', exact: true }).click()
  await expect(settings.getByRole('status')).toContainText('Videoland')
  await settings.getByRole('button', { name: 'Save subscriptions' }).click()
  await expect(settings.getByRole('status')).toHaveText('Subscriptions saved.')
  await page.reload()
  await expect(settings.getByRole('button', { name: 'Streaming country' })).toHaveText('United States')
  await expect(settings.getByRole('checkbox', { name: 'Videoland' })).toHaveCount(0)
})
