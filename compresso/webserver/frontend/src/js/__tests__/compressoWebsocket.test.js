import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock quasar before importing module under test
vi.mock('quasar', () => ({
  Notify: { create: vi.fn() },
}))

// Mock compressoGlobals default export with the properties accessed by compressoWebsocket.js
vi.mock('../compressoGlobals', () => ({
  default: {
    ws: undefined,
    websocketEventListeners: {},
    frontendMessage: {},
  },
}))

import { Notify } from 'quasar'
import $compressoMock from '../compressoGlobals'
import { wsConnectionState, CompressoWebsocketHandler } from '../compressoWebsocket'

// ---------------------------------------------------------------------------
// WebSocket mock
// ---------------------------------------------------------------------------
class MockWebSocket {
  constructor(url) {
    this.url = url
    this.readyState = MockWebSocket.CONNECTING
    this._listeners = {}
    MockWebSocket._lastInstance = this
    MockWebSocket._instances.push(this)
  }

  addEventListener(type, cb) {
    if (!this._listeners[type]) this._listeners[type] = []
    this._listeners[type].push(cb)
  }

  removeEventListener(type, cb) {
    if (!this._listeners[type]) return
    this._listeners[type] = this._listeners[type].filter((fn) => fn !== cb)
  }

  send(data) {
    this._lastSent = data
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this._trigger('close')
  }

  _trigger(type, event = {}) {
    const cbs = this._listeners[type] || []
    cbs.forEach((fn) => fn(event))
  }

  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static _lastInstance = null
  static _instances = []
}

// ---------------------------------------------------------------------------
// Helpers to reset shared state between tests
// ---------------------------------------------------------------------------
function resetGlobalsMock() {
  $compressoMock.ws = undefined
  $compressoMock.websocketEventListeners = {}
  $compressoMock.frontendMessage = {}
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('wsConnectionState', () => {
  it('starts as disconnected', () => {
    expect(wsConnectionState.value).toBe('disconnected')
  })
})

describe('CompressoWebsocketHandler factory', () => {
  it('returns an object with init, close, addEventListener, removeEventListener', () => {
    const $t = (k) => k
    const handler = CompressoWebsocketHandler($t)
    expect(handler).toHaveProperty('init')
    expect(handler).toHaveProperty('close')
    expect(handler).toHaveProperty('addEventListener')
    expect(handler).toHaveProperty('removeEventListener')
    expect(typeof handler.init).toBe('function')
    expect(typeof handler.close).toBe('function')
    expect(typeof handler.addEventListener).toBe('function')
    expect(typeof handler.removeEventListener).toBe('function')
  })
})

describe('addEventListener / removeEventListener', () => {
  let handler

  beforeEach(() => {
    resetGlobalsMock()
    vi.useFakeTimers()
    MockWebSocket._lastInstance = null
    MockWebSocket._instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal('window', {
      location: { protocol: 'http:', host: 'localhost:8080' },
    })
    vi.spyOn(globalThis, 'localStorage', 'get').mockReturnValue({
      getItem: () => null,
    })
    const $t = (k) => k
    handler = CompressoWebsocketHandler($t)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('registers a listener in the registry', () => {
    const cb = vi.fn()
    handler.addEventListener('message', 'test_listener', cb)
    expect($compressoMock.websocketEventListeners['test_listener']).toBeDefined()
    expect($compressoMock.websocketEventListeners['test_listener'].type).toBe('message')
    expect($compressoMock.websocketEventListeners['test_listener'].callback).toBe(cb)
  })

  it('is idempotent when same key, type, and callback are re-registered', () => {
    const cb = vi.fn()
    handler.addEventListener('message', 'test_listener', cb)
    handler.addEventListener('message', 'test_listener', cb)
    // Still only one entry
    expect(Object.keys($compressoMock.websocketEventListeners)).toContain('test_listener')
    expect(Object.keys($compressoMock.websocketEventListeners)).toHaveLength(1)
    expect($compressoMock.websocketEventListeners['test_listener'].callback).toBe(cb)
  })

  it('replaces the old callback when same key but different callback', () => {
    const cb1 = vi.fn()
    const cb2 = vi.fn()
    handler.addEventListener('message', 'test_listener', cb1)
    handler.addEventListener('message', 'test_listener', cb2)
    expect($compressoMock.websocketEventListeners['test_listener'].callback).toBe(cb2)
  })

  it('removeEventListener removes the entry from the registry', () => {
    const cb = vi.fn()
    handler.addEventListener('message', 'test_listener', cb)
    expect($compressoMock.websocketEventListeners['test_listener']).toBeDefined()
    handler.removeEventListener('test_listener')
    expect($compressoMock.websocketEventListeners['test_listener']).toBeUndefined()
  })

  it('removeEventListener with an unknown key does nothing', () => {
    expect(() => handler.removeEventListener('nonexistent_key')).not.toThrow()
  })
})

describe('close()', () => {
  let handler

  beforeEach(() => {
    resetGlobalsMock()
    vi.useFakeTimers()
    MockWebSocket._lastInstance = null
    MockWebSocket._instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal('window', {
      location: { protocol: 'http:', host: 'localhost:8080' },
    })
    vi.spyOn(globalThis, 'localStorage', 'get').mockReturnValue({
      getItem: () => null,
    })
    const $t = (k) => k
    handler = CompressoWebsocketHandler($t)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    wsConnectionState.value = 'disconnected'
  })

  it('sets wsConnectionState to disconnected', () => {
    // Manually plant a mock ws so close() can operate on it
    const mockWs = new MockWebSocket('ws://localhost:8080/compresso/websocket')
    mockWs.__compressoBoundListenerKeys = new Set()
    $compressoMock.ws = mockWs
    wsConnectionState.value = 'connected'

    handler.close()

    expect(wsConnectionState.value).toBe('disconnected')
  })

  it('calls ws.close() on the active socket', () => {
    const mockWs = new MockWebSocket('ws://localhost:8080/compresso/websocket')
    mockWs.__compressoBoundListenerKeys = new Set()
    const closeSpy = vi.spyOn(mockWs, 'close')
    $compressoMock.ws = mockWs

    handler.close()

    expect(closeSpy).toHaveBeenCalled()
  })

  it('sets $compresso.ws to null after close', () => {
    const mockWs = new MockWebSocket('ws://localhost:8080/compresso/websocket')
    mockWs.__compressoBoundListenerKeys = new Set()
    $compressoMock.ws = mockWs

    handler.close()

    expect($compressoMock.ws).toBeNull()
  })
})

describe('init() — basic', () => {
  beforeEach(() => {
    resetGlobalsMock()
    vi.useFakeTimers()
    MockWebSocket._lastInstance = null
    MockWebSocket._instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.spyOn(globalThis, 'localStorage', 'get').mockReturnValue({
      getItem: () => null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    wsConnectionState.value = 'disconnected'
  })

  it('creates a WebSocket with the correct ws:// URL from window.location', () => {
    vi.stubGlobal('window', {
      location: { protocol: 'http:', host: 'localhost:8080' },
    })
    const $t = (k) => k
    const handler = CompressoWebsocketHandler($t)
    handler.init()

    expect(MockWebSocket._lastInstance).not.toBeNull()
    expect(MockWebSocket._lastInstance.url).toBe('ws://localhost:8080/compresso/websocket')
  })

  it('sets wsConnectionState to connecting when init is called', () => {
    vi.stubGlobal('window', {
      location: { protocol: 'http:', host: 'localhost:8080' },
    })
    const $t = (k) => k
    const handler = CompressoWebsocketHandler($t)

    wsConnectionState.value = 'disconnected'
    handler.init()

    expect(wsConnectionState.value).toBe('connecting')
  })

  it('uses wss: when window.location.protocol is https:', () => {
    vi.stubGlobal('window', {
      location: { protocol: 'https:', host: 'example.com' },
    })
    const $t = (k) => k
    const handler = CompressoWebsocketHandler($t)
    handler.init()

    expect(MockWebSocket._lastInstance).not.toBeNull()
    expect(MockWebSocket._lastInstance.url).toMatch(/^wss:\/\//)
    expect(MockWebSocket._lastInstance.url).toBe('wss://example.com/compresso/websocket')
  })
})
