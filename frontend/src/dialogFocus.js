export function trapDialogTab(event, dialog) {
  if (!dialog || event.key !== 'Tab') return
  const controls = [...dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]')]
  if (!controls.length) { event.preventDefault(); dialog.focus(); return }
  const first = controls[0], last = controls.at(-1)
  if (event.shiftKey && globalThis.document?.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && globalThis.document?.activeElement === last) { event.preventDefault(); first.focus() }
}
