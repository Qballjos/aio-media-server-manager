/** Display size belongs to this browser, independently of profile/theme sync. */
import { computed, ref } from 'vue'

export const DISPLAY_SIZES = [
  { value: 'compact', label: 'Compact', scale: 0.85 },
  { value: 'small', label: 'Small', scale: 0.9 },
  { value: 'standard', label: 'Standard', scale: 1 },
  { value: 'large', label: 'Large', scale: 1.1 },
]
const KEY = 'amm-display-size'
export const displaySize = ref('standard')
export const displayScale = computed(() => DISPLAY_SIZES.find(item => item.value === displaySize.value).scale)

export function setDisplaySize(value) {
  displaySize.value = DISPLAY_SIZES.some(item => item.value === value) ? value : 'standard'
  if (typeof document !== 'undefined') document.documentElement.style.setProperty('--display-scale', String(displayScale.value))
  try { localStorage.setItem(KEY, displaySize.value) } catch (_) { /* Keep the selection for this session when storage is unavailable. */ }
}

export function initDisplaySize() {
  let saved
  try { saved = localStorage.getItem(KEY) } catch (_) { /* Use the default when storage is unavailable. */ }
  setDisplaySize(saved)
}
