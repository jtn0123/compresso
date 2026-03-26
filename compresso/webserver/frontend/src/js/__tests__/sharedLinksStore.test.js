import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('quasar', () => ({ setCssVar: vi.fn(), Notify: { create: vi.fn() } }))
vi.mock('src/js/compressoGlobals', async () => {
  const actual = await vi.importActual('src/js/compressoGlobals')
  return {
    ...actual,
    showEventToast: vi.fn(),
  }
})

// Mock location.reload — jsdom/happy-dom does not allow reassigning it directly,
// so we use Object.defineProperty once before the suite runs.
const reloadMock = vi.fn()
Object.defineProperty(window, 'location', {
  value: { ...window.location, reload: reloadMock },
  writable: true,
})

import axios from 'axios'
import { sharedLinksStore } from '../sharedLinksStore'

// Helper: build a well-formed API response
function makeResponse({ remote_installations, installation_name } = {}) {
  return {
    data: {
      settings: {
        ...(remote_installations !== undefined && { remote_installations }),
        ...(installation_name !== undefined && { installation_name }),
      },
    },
  }
}

// Reset the store's mutable state and all mocks before every test.
beforeEach(() => {
  sharedLinksStore.target = 'local'
  sharedLinksStore.availableLinks = []
  sharedLinksStore.localName = ''
  vi.clearAllMocks()
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------
describe('initial state', () => {
  it('defaults target to "local" when localStorage has no item', async () => {
    // Re-evaluate the module with a clean localStorage to observe the
    // default value that is captured at import time.
    localStorage.removeItem('compresso-installation-target')
    vi.resetModules()
    const { sharedLinksStore: fresh } = await import('../sharedLinksStore')
    expect(fresh.target).toBe('local')
  })

  it('picks up a stored target from localStorage at import time', async () => {
    localStorage.setItem('compresso-installation-target', 'remote-1')
    vi.resetModules()
    const { sharedLinksStore: fresh } = await import('../sharedLinksStore')
    expect(fresh.target).toBe('remote-1')
    // Tidy up so other tests are not affected
    localStorage.removeItem('compresso-installation-target')
  })

  it('availableLinks defaults to empty array', () => {
    expect(sharedLinksStore.availableLinks).toEqual([])
  })

  it('localName defaults to empty string', () => {
    expect(sharedLinksStore.localName).toBe('')
  })
})

// ---------------------------------------------------------------------------
// fetchLinks — success path
// ---------------------------------------------------------------------------
describe('fetchLinks success', () => {
  it('sets availableLinks from the response', async () => {
    const links = [{ name: 'server-a', url: 'http://a' }]
    axios.get.mockResolvedValueOnce(makeResponse({ remote_installations: links, installation_name: 'main' }))

    await sharedLinksStore.fetchLinks()

    expect(sharedLinksStore.availableLinks).toEqual(links)
  })

  it('sets localName from the response', async () => {
    axios.get.mockResolvedValueOnce(makeResponse({ remote_installations: [], installation_name: 'primary' }))

    await sharedLinksStore.fetchLinks()

    expect(sharedLinksStore.localName).toBe('primary')
  })

  it('calls the correct API URL with skipProxy: true', async () => {
    axios.get.mockResolvedValueOnce(makeResponse({ remote_installations: [], installation_name: '' }))

    await sharedLinksStore.fetchLinks()

    expect(axios.get).toHaveBeenCalledOnce()
    const [url, options] = axios.get.mock.calls[0]
    expect(url).toMatch(/v2\/settings\/read$/)
    expect(options).toMatchObject({ skipProxy: true })
  })
})

// ---------------------------------------------------------------------------
// fetchLinks — missing / partial fields
// ---------------------------------------------------------------------------
describe('fetchLinks with missing fields', () => {
  it('defaults availableLinks to [] when remote_installations is undefined', async () => {
    axios.get.mockResolvedValueOnce(makeResponse({ installation_name: 'x' }))

    await sharedLinksStore.fetchLinks()

    expect(sharedLinksStore.availableLinks).toEqual([])
  })

  it('defaults localName to "" when installation_name is undefined', async () => {
    axios.get.mockResolvedValueOnce(makeResponse({ remote_installations: [] }))

    await sharedLinksStore.fetchLinks()

    expect(sharedLinksStore.localName).toBe('')
  })
})

// ---------------------------------------------------------------------------
// fetchLinks — error path
// ---------------------------------------------------------------------------
describe('fetchLinks error', () => {
  it('logs the error to console.error via logger', async () => {
    const err = new Error('network failure')
    axios.get.mockRejectedValueOnce(err)
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    await sharedLinksStore.fetchLinks()

    expect(spy).toHaveBeenCalledWith('[SharedLinks]', 'Failed to fetch shared links')
  })

  it('resets availableLinks to [] on error', async () => {
    sharedLinksStore.availableLinks = [{ name: 'stale' }]
    axios.get.mockRejectedValueOnce(new Error('timeout'))
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    await sharedLinksStore.fetchLinks()

    expect(sharedLinksStore.availableLinks).toEqual([])
    spy.mockRestore()
  })

  it('does not crash or throw when the request fails', async () => {
    axios.get.mockRejectedValueOnce(new Error('boom'))
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    await expect(sharedLinksStore.fetchLinks()).resolves.toBeUndefined()
    spy.mockRestore()
  })
})

// ---------------------------------------------------------------------------
// setTarget
// ---------------------------------------------------------------------------
describe('setTarget', () => {
  it('updates the target property on the store', () => {
    sharedLinksStore.setTarget('remote-node')

    expect(sharedLinksStore.target).toBe('remote-node')
  })

  it('persists the new target in localStorage', () => {
    sharedLinksStore.setTarget('remote-node')

    expect(localStorage.getItem('compresso-installation-target')).toBe('remote-node')
  })

  it('calls location.reload()', () => {
    sharedLinksStore.setTarget('any-target')

    expect(reloadMock).toHaveBeenCalledOnce()
  })
})
