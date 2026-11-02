import { createApp } from 'vue'
import './style.css'
import './dashboard.css'
import App from './App.vue'
import { i18n, initLocale } from './i18n/index.js'
import { router } from './router'
import { initPwaInstall } from './pwaInstall.js'
import { initTheme } from './theme.js'
import { initWallpaper } from './background.js'
import { initGlass } from './glass.js'
import { initAccentFromCache, loadBranding } from './branding.js'

initLocale()
initTheme()
initGlass()
initWallpaper()
initAccentFromCache()
initPwaInstall()
loadBranding()

if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}

createApp(App).use(router).use(i18n).mount('#app')
