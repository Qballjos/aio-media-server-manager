import { startAuthentication, startRegistration } from '@simplewebauthn/browser'
import { apiError, apiJson } from './api.js'
import { t } from './i18n/index.js'

export function canUsePasskeys() {
  const { hostname } = window.location
  const isIpAddress = hostname.startsWith('[') || /^[\d.]+$/.test(hostname)
  return window.isSecureContext && !isIpAddress && Boolean(window.PublicKeyCredential)
}

export async function requestPasskey(action, body) {
  const { res, data } = await apiJson('/api/auth/passkeys' + action, body === undefined ? {} : {
    method: 'POST',
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(t(apiError(data, 'Could not verify the passkey.')))
  return data
}

export async function usePasskey(action, body = {}) {
  const optionsJSON = await requestPasskey(`/${action}/options`, body)
  let credential
  try {
    credential = action === 'register'
      ? await startRegistration({ optionsJSON })
      : await startAuthentication({ optionsJSON })
  } catch {
    throw new Error(t('Passkey prompt cancelled or unavailable.'))
  }
  return requestPasskey(`/${action}`, {
    challenge: optionsJSON.challenge,
    credential: JSON.stringify(credential),
  })
}
