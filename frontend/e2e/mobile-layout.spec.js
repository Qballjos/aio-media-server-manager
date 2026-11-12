import { test, expect } from '@playwright/test'
import { TABLE } from '../src/i18n/locales/table.js'

test.use({ serviceWorkers: 'block' })

test.beforeEach(async ({ page }, testInfo) => {
  const language = testInfo.project.metadata.language || 'nl'
  await page.route('**/health', route => route.fulfill({ json: { status: 'ok' } }))
  const apps = [
    { name: 'sonarr', display_name: 'Sonarr', description: 'TV series automation for Usenet and BitTorrent.', category: 'automation', state: 'running', installed: true, daemon: true, port: 8989 },
    { name: 'jellyfin', display_name: 'Jellyfin', description: 'Free media server for movies, TV, and music with optional hardware transcoding.', category: 'media', state: 'running', installed: true, daemon: true, port: 8096 },
    { name: 'seerr', display_name: 'Seerr', description: 'Request management UI that connects to Sonarr, Radarr, Jellyfin, and Plex.', category: 'requests', state: 'running', installed: true, daemon: true, port: 5055 },
  ]
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let json = {}
    if (['/api/auth/status', '/api/auth/visuals', '/api/auth/me'].includes(path)) {
      json = { authenticated: true, setup_required: false, username: 'fixture', locale: language, theme: 'dark', wallpaper: 'aurora', has_avatar: true, avatar_url: '/app-icons/seerr.svg' }
    } else if (path === '/api/wizard/status') json = { completed: true }
    else if (path === '/api/catalog' || path === '/api/applications') json = { applications: apps }
    else if (path === '/api/homepage') {
      json = { apps, recent: [], requests: [], downloads: [], widgets: [], waiting: [], seerr: { available: true },
        trending: ['missing', 'requested', 'available', 'partial', 'deleted', 'monitored'].map((status, index) => ({ title: `Trending ${status}`, mediaType: 'movie', mediaId: index + 1, poster: '/pwa-192.png', status })),
        calendar: [{ title: 'Today fixture', source: 'sonarr', kind: 'episode', when: new Date().toISOString() }] }
    } else if (path === '/api/homepage/downloads') json = { downloads: [] }
    else if (path === '/api/homepage/recent' || path === '/api/homepage/trending') json = { items: [] }
    await route.fulfill({ json })
  })
})

test('Home, Catalog and Settings controls fit their screen size', async ({ page }, testInfo) => {
  const language = testInfo.project.metadata.language || 'nl'
  const tr = key => language === 'en' ? key : TABLE[key][['nl', 'de', 'fr'].indexOf(language)]
  const mobile = page.viewportSize().width <= 760
  await page.goto('/#/home')
  const trending = page.locator('.home-card-trending')
  await expect(trending.locator('.home-tile')).toHaveCount(1)
  const title = await trending.locator('h3').boundingBox()
  const filters = await trending.locator('.home-type-filter').boundingBox()
  await expect(trending.locator('.home-trending-toggle')).toHaveCount(0)
  await expect(trending.locator('.home-tile')).toContainText('Trending missing')
  if (mobile) {
    expect(filters.x).toBeGreaterThanOrEqual(title.x + title.width)
    expect(Math.abs(filters.y + filters.height / 2 - title.y - title.height / 2)).toBeLessThan(2)
    await expect(page.locator('.cal-mode-day')).toBeVisible()
  } else await expect(page.locator('.cal-list, .cal-mode-week')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await trending.scrollIntoViewIfNeeded()
  await expect.poll(() => trending.locator('img').first().evaluate(img => img.naturalWidth)).toBeGreaterThan(0)
  await page.screenshot({ path: testInfo.outputPath('home.png'), animations: 'disabled' })

  await page.goto('/#/catalog')
  const filterButton = page.locator('.catalog-filters-toggle')
  const categoryNav = page.locator('#catalog-category-navigation')
  if (mobile) {
    await expect(filterButton).toHaveAttribute('aria-expanded', 'false')
    await expect(categoryNav).toBeHidden()
    await expect(page.locator('.catalog-status-nav button')).toHaveCount(4)
    await page.screenshot({ path: testInfo.outputPath('catalog.png'), animations: 'disabled' })
    await filterButton.click()
    await expect(categoryNav).toBeVisible()
    const mediaCategory = categoryNav.getByRole('button', { name: tr('Media'), exact: true })
    await mediaCategory.focus()
    await mediaCategory.press('Enter')
    await expect(categoryNav).toBeHidden()
    await expect(filterButton).toBeFocused()
    await expect(filterButton).toContainText(tr('Media'))
    await expect(page).toHaveURL(/cat=media/)
    await filterButton.click()
    await categoryNav.getByRole('button', { name: tr('All categories'), exact: true }).click()
    await expect(page).not.toHaveURL(/cat=/)
  } else {
    await expect(filterButton).toBeHidden()
    await expect(categoryNav).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('catalog.png'), animations: 'disabled' })
  }

  await page.goto('/#/settings/account')
  const settingsPicker = page.locator('.settings-mobile-select')
  if (mobile) {
    await expect(settingsPicker).toHaveValue('account')
    await page.screenshot({ path: testInfo.outputPath('settings.png'), animations: 'disabled' })
    await settingsPicker.selectOption('visuals')
    await expect(page).toHaveURL(/settings\/visuals/)
    await expect(page.locator('#settings-navigation')).toBeHidden()
    await page.getByRole('heading', { name: tr('Display size'), exact: true }).waitFor()
    await page.screenshot({ path: testInfo.outputPath('visuals.png'), animations: 'disabled' })
  } else {
    await expect(settingsPicker).toBeHidden()
    await expect(page.locator('#settings-navigation')).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('settings.png'), animations: 'disabled' })
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
