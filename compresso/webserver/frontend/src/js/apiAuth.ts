const API_TOKEN_STORAGE_KEY = 'compresso-api-token'
const WEBSOCKET_AUTH_PROTOCOL_PREFIX = 'compresso-auth.'

export function getApiToken(): string {
  return globalThis.sessionStorage.getItem(API_TOKEN_STORAGE_KEY) || ''
}

export function setApiToken(token: string | null | undefined): string {
  const normalized = String(token || '').trim()
  if (normalized) {
    globalThis.sessionStorage.setItem(API_TOKEN_STORAGE_KEY, normalized)
  } else {
    globalThis.sessionStorage.removeItem(API_TOKEN_STORAGE_KEY)
  }
  return normalized
}

function encodeWebsocketToken(token: string): string {
  const bytes = new TextEncoder().encode(token)
  let binary = ''
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte)
  })
  return globalThis.btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '')
}

export function getWebsocketProtocols(): string[] | undefined {
  const token = getApiToken()
  if (!token) return undefined
  return ['compresso', `${WEBSOCKET_AUTH_PROTOCOL_PREFIX}${encodeWebsocketToken(token)}`]
}

export function promptForApiToken(promptText: string): string {
  const token = globalThis.prompt(promptText)
  return token === null ? '' : setApiToken(token)
}
