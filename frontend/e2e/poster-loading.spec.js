import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

// Keep the pass-through service worker from bypassing the synthetic API routes on reload.
test.use({ serviceWorkers: 'block' })

test('a cold Home load defers offscreen posters in a large requests rail', async ({ page }, testInfo) => {
  const poster = readFileSync(new URL('../public/pwa-192.png', import.meta.url))
  const fetched = new Set()
  await page.route('**/poster-fixture/**', async route => {
    fetched.add(new URL(route.request().url()).pathname)
    await route.fulfill({ contentType: 'image/png', body: poster })
  })
  const apps = [{ name: 'seerr', display_name: 'Seerr', state: 'running', port: 5055, url: 'http://localhost:5055', sick: false }]
  const items = Array.from({ length: 350 }, (_, index) => ({
    title: `Request ${index + 1}`, source: 'seerr', mediaType: 'movie', mediaId: index + 1,
    status: 'available', poster: `/poster-fixture/${index + 1}.png`,
  }))
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let json = {}
    if (path === '/api/auth/status' || path === '/api/auth/visuals') {
      json = { authenticated: true, setup_required: false, username: 'fixture', locale: 'en', theme: 'dark', wallpaper: 'aurora' }
    } else if (path === '/api/wizard/status') json = { completed: true }
    else if (path === '/api/catalog' || path === '/api/applications') json = { applications: apps }
    else if (path === '/api/homepage') {
      json = { apps, recent: [], requests: items, trending: [], calendar: [], downloads: [], seerr: { available: true }, widgets: [], waiting: [] }
    } else if (path === '/api/homepage/downloads') json = { downloads: [] }
    else if (path === '/api/homepage/trending' || path === '/api/homepage/recent') json = { items: [] }
    await route.fulfill({ json })
  })

  for (const coldLoad of ['initial', 'reload']) {
    fetched.clear()
    if (coldLoad === 'initial') await page.goto('/#/home')
    else await page.reload()
    const rail = page.locator('[data-widget="requests"] .home-rail')
    await expect(rail.locator('.home-tile')).toHaveCount(350)
    await rail.scrollIntoViewIfNeeded()
    await expect.poll(() => fetched.size).toBeGreaterThan(0)
    // A slow browser must not pass merely because the other downloads have not started yet.
    await page.waitForTimeout(500)
    expect(fetched.size).toBeLessThan(20)
    await expect(rail.locator('img').last()).not.toHaveAttribute('src', /poster-fixture/)
    if (coldLoad === 'initial') {
      await page.screenshot({ path: testInfo.outputPath('visible-posters.png') })
    }

    // Scrolling must still make the final request available, without fetching the whole rail.
    await rail.evaluate(node => { node.scrollLeft = node.scrollWidth })
    await expect.poll(() => fetched.has('/poster-fixture/350.png')).toBe(true)
    expect(fetched.size).toBeLessThan(40)
    await expect(rail.locator('img').first()).not.toHaveAttribute('src', /poster-fixture/)
  }
})
