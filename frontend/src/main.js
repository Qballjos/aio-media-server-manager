import { createApp } from 'vue'
import './style.css'
import './dashboard.css'
import App from './App.vue'
import { router } from './router'
import { initPwaInstall } from './pwaInstall.js'
import { initTheme } from './theme.js'
import { initWallpaper } from './background.js'
import { initAccentFromCache, loadBranding } from './branding.js'

initTheme()
initWallpaper()
initAccentFromCache()
initPwaInstall()
loadBranding()

if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}

createApp(App).use(router).mount('#app')
