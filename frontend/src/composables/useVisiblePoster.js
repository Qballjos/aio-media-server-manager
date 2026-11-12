import { onMounted, onUnmounted, ref } from 'vue'

// One observer for all rails. Intersection includes clipping by their scroll containers;
// native loading="lazy" can eagerly fetch an entire horizontal rail in WebKit.
const listeners = new Map()
let observer = null

export function useVisiblePoster(element) {
  const visible = ref(false)
  let target = null

  onMounted(() => {
    target = element.value
    if (typeof IntersectionObserver === 'undefined') {
      visible.value = true
      return
    }
    if (!observer) {
      observer = new IntersectionObserver(entries => {
        for (const entry of entries) listeners.get(entry.target)?.(entry.isIntersecting)
      }, { rootMargin: '160px 0px' })
    }
    listeners.set(target, value => { visible.value = value })
    observer.observe(target)
  })

  onUnmounted(() => {
    if (!target || !observer) return
    observer.unobserve(target)
    listeners.delete(target)
    if (!listeners.size) {
      observer.disconnect()
      observer = null
    }
  })

  return visible
}
