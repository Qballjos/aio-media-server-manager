/** Copy text on HTTPS/localhost and plain http://LAN (Clipboard API is secure-context only). */
export async function copyText(text) {
  const value = String(text ?? '')
  if (!value) throw new Error('Nothing to copy.')

  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return
    } catch {
      // Fall through — common on http://192.168.x.x (not a secure context).
    }
  }

  const input = document.createElement('textarea')
  input.value = value
  input.setAttribute('readonly', '')
  input.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;border:0;padding:0;margin:0'
  document.body.appendChild(input)
  input.focus()
  input.select()
  input.setSelectionRange(0, value.length)
  let ok = false
  try {
    ok = document.execCommand('copy')
  } finally {
    input.remove()
  }
  if (!ok) throw new Error('Copy command was rejected.')
}
