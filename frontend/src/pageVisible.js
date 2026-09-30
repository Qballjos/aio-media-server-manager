/** Skip background polls while the tab is hidden; catch up when it is shown again. */

export function isPageVisible() {
  return typeof document === 'undefined' || document.visibilityState === 'visible'
}

export function startGuardedInterval(fn, ms, { immediate = false } = {}) {
  const tick = () => {
    if (isPageVisible()) fn()
  }
  const timer = setInterval(tick, ms)
  const onVis = () => {
    if (isPageVisible()) fn()
  }
  document.addEventListener('visibilitychange', onVis)
  if (immediate) tick()
  return () => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', onVis)
  }
}
