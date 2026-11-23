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
        calendar: [] }
    } else if (path === '/api/homepage/calendar') {
      json = { items: [{ title: 'Today fixture', source: 'sonarr', kind: 'episode', when: new Date().toISOString() }] }
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
  const settingsPicker = page.locator('#settings-section-select')
  if (mobile) {
    await expect(settingsPicker).toContainText(tr('Profile'))
    await page.screenshot({ path: testInfo.outputPath('settings.png'), animations: 'disabled' })
    await settingsPicker.click()
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('settings-picker.png'), animations: 'disabled' })
    await settingsPicker.press('Escape')
    await expect(page.getByRole('listbox')).toBeHidden()
    await expect(settingsPicker).toBeFocused()
    await settingsPicker.press('Enter')
    await settingsPicker.press('ArrowDown')
    await settingsPicker.press('Enter')
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

test('Catalog installation history stays inside its dialog', async ({ page }, testInfo) => {
  await page.route('**/api/catalog/install-jobs', route => route.fulfill({ json: { jobs: [{
    name: 'cleanup', status: 'installing', message: 'Downloading',
    history: Array.from({ length: 200 }, (_, i) => ({ at: 1700000000 + i, message: `Downloading ${i}: ${'long-download-path/'.repeat(12)}` })),
  }] } }))
  await page.goto('/#/catalog')
  const language = testInfo.project.metadata.language || 'nl'
  const activity = TABLE['Installation activity'][['nl', 'de', 'fr'].indexOf(language)]
  await page.getByRole('button', { name: activity, exact: true }).click()
  const dialog = page.locator('.activity-dialog')
  const body = dialog.locator('.activity-body')
  await expect(dialog).toBeVisible()
  expect(await body.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true)
  await body.evaluate(el => { el.scrollTop = el.scrollHeight })
  const bounds = await dialog.boundingBox()
  expect(bounds.y).toBeGreaterThanOrEqual(0)
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(page.viewportSize().height)
  expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
  await expect(dialog.locator('.share-row button')).toBeInViewport()
  await page.screenshot({ path: testInfo.outputPath('installation-history.png'), animations: 'disabled' })
  await dialog.locator('.share-row button').click()
  await expect(dialog).toBeHidden()
})

test('Streaming settings and Trending logos fit in light and dark themes', async ({ page }, testInfo) => {
  const language = testInfo.project.metadata.language || 'nl'
  const tr = key => TABLE[key][['nl', 'de', 'fr'].indexOf(language)]
  const netflix = { id: 8, name: 'Netflix', logo_url: '/pwa-192.png' }
  const unavailable = { id: 9, name: 'Provider without artwork', logo_url: '/missing-logo.png' }
  const providers = [netflix, unavailable, { id: 10, name: 'Zee5', logo_url: '/pwa-192.png' },
    ...Array.from({ length: 23 }, (_, i) => ({ id: 30 + i, name: `Regional service ${i + 1}`, logo_url: '/pwa-192.png' }))]
  await page.route('**/missing-logo.png', route => route.abort())
  await page.route('**/api/streaming/admin/**', route => {
    const url = new URL(route.request().url())
    return route.fulfill({ json: url.pathname.endsWith('/preferences')
      ? { country: 'NL', provider_ids: [8] }
      : url.searchParams.has('country') ? { providers } : { regions: ['NL'] } })
  })
  await page.route('**/api/homepage/title?**', route => route.fulfill({ json: {
    title: 'Trending missing', poster: '/pwa-192.png', overview: 'A synthetic title overview.',
    streaming: { configured: true, providers: [netflix, unavailable], link: 'https://www.themoviedb.org/movie/1/watch' },
  } }))
  const fits = locator => expect.poll(() => locator.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)

  let theme = 'dark'
  await page.route('**/api/auth/**', route => {
    const path = new URL(route.request().url()).pathname
    if (!['/api/auth/status', '/api/auth/visuals', '/api/auth/me'].includes(path)) return route.fallback()
    return route.fulfill({ json: {
      authenticated: true, setup_required: false, username: 'fixture', locale: language, theme, wallpaper: 'aurora',
    } })
  })

  for (theme of ['dark', 'light']) {
    await page.goto(`/?fixture-theme=${theme}#/settings/account`)
    const settings = page.getByRole('region', { name: tr('Streaming subscriptions') })
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
    await expect(settings.getByRole('checkbox', { name: 'Netflix' })).toBeChecked()
    expect((await settings.getByRole('checkbox', { name: 'Netflix' }).locator('..').boundingBox()).height).toBeGreaterThanOrEqual(44)
    const options = settings.getByRole('group', { name: tr('Streaming subscriptions') })
    await expect(options.getByRole('checkbox')).toHaveCount(26)
    const columns = await options.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length)
    expect(columns).toBe(testInfo.project.name === 'desktop-webkit' ? 3 : testInfo.project.name === 'small-mobile-webkit' ? 1 : 2)
    await expect(options.getByRole('checkbox', { name: 'Zee5' })).toBeVisible()
    expect(await options.evaluate(el => el.scrollHeight <= el.clientHeight + 1)).toBe(true)
    await fits(settings)
    await fits(page.locator('html'))
    await settings.screenshot({ path: testInfo.outputPath(`streaming-settings-${theme}.png`) })

    await page.goto('/#/home')
    await page.locator('.home-tile-trending .home-tile-link').click()
    const title = page.getByRole('dialog')
    const availability = title.getByRole('region', { name: tr('Streaming availability') })
    await expect(availability.getByRole('img', { name: 'Netflix' })).toBeVisible()
    await expect(availability.getByText('Netflix', { exact: true })).toBeHidden()
    await expect(availability.getByText('Provider without artwork')).toBeVisible()
    const body = await title.locator('.home-title-body').boundingBox()
    const streaming = await availability.boundingBox()
    expect(streaming.width).toBeGreaterThanOrEqual(body.width)
    expect(streaming.y).toBeGreaterThanOrEqual(body.y + body.height)
    await fits(title)
    await fits(page.locator('html'))
    await title.screenshot({ path: testInfo.outputPath(`streaming-popup-${theme}.png`) })
  }
})

test('Now playing scrolls through concurrent streams inside the widget', async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    const playing = [{ id: 'playing', x: 0, y: 0, w: 4, h: 3 }]
    localStorage.setItem('amm-home-grid', JSON.stringify({ desktop: playing, tablet: playing, phone: playing }))
  })
  await page.route('**/api/homepage/status', route => route.fulfill({ json: {
    playing: [
      { title: 'Living room stream', device: 'TV', source: 'jellyfin', progress: 25, poster: '/pwa-192.png' },
      { title: 'Bedroom stream', device: 'Tablet', source: 'plex', progress: 50 },
    ],
  } }))
  await page.goto('/#/home')
  const widget = page.locator('.home-card-playing')
  const title = name => widget.getByText(name, { exact: true })
  const first = title('Living room stream')
  const second = title('Bedroom stream')
  await expect(first).toBeInViewport()
  await expect(second).not.toBeInViewport()
  const scroller = widget.locator('.np-scroll')
  expect(await scroller.evaluate(el => el.scrollWidth > el.clientWidth && el.scrollHeight === el.clientHeight)).toBe(true)
  await scroller.focus()
  await expect.poll(() => widget.evaluate(el => {
    const body = el.closest('.hg-body')
    return body.getBoundingClientRect().top < body.parentElement.getBoundingClientRect().top
  })).toBe(true)
  await page.keyboard.press('ArrowRight')
  await expect(second).toBeInViewport()
  await expect(first).not.toBeInViewport()
  await expect.poll(() => scroller.evaluate(el => Math.abs(el.scrollWidth - el.clientWidth - el.scrollLeft))).toBeLessThan(2)
  await widget.screenshot({ path: testInfo.outputPath('now-playing-second.png') })
  if (testInfo.project.name === 'desktop-webkit') {
    await scroller.hover()
    await page.mouse.wheel(-await scroller.evaluate(el => el.clientWidth), 0)
  } else {
    await page.keyboard.press('ArrowLeft')
  }
  await expect(first).toBeInViewport()
  await expect(second).not.toBeInViewport()
  await expect.poll(() => scroller.evaluate(el => Math.abs(el.scrollLeft))).toBeLessThan(2)
  await widget.screenshot({ path: testInfo.outputPath('now-playing-first.png') })
})

test('Dock tiles rise above the glass base without clipping', async ({ page }, testInfo) => {
  await page.goto('/#/home')
  const dock = page.locator('.home-dock.is-floating')
  const tile = dock.locator('.home-app').first()
  await expect(tile).toBeVisible()
  const getBounds = () => tile.evaluate(el => {
    const tile = el.getBoundingClientRect()
    const row = el.parentElement.getBoundingClientRect()
    const base = el.closest('.home-dock').querySelector('.home-dock-base').getBoundingClientRect()
    return { top: tile.top, height: tile.height, rowTop: row.top, baseTop: base.top }
  })
  const resting = await getBounds()
  expect(resting.top).toBeLessThan(resting.baseTop)
  if (await page.evaluate(() => matchMedia('(hover: hover) and (pointer: fine)').matches)) {
    await tile.hover()
    await expect.poll(async () => (await getBounds()).height / resting.height).toBeGreaterThan(1.15)
    const raised = await getBounds()
    expect(raised.top).toBeLessThan(resting.top)
    expect(raised.top).toBeGreaterThanOrEqual(raised.rowTop)
  }
  await dock.screenshot({ path: testInfo.outputPath('dock.png'), animations: 'disabled' })
})
