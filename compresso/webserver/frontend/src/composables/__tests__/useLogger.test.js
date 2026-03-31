import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock showEventToast before importing the module under test
const showEventToastMock = vi.fn()
vi.mock('src/js/compressoGlobals', () => ({
  showEventToast: (...args) => showEventToastMock(...args),
}))

import { createLogger, useLogger } from '../useLogger'

describe('createLogger', () => {
  let originalEnv

  beforeEach(() => {
    originalEnv = process.env.NODE_ENV
    vi.clearAllMocks()
  })

  afterEach(() => {
    process.env.NODE_ENV = originalEnv
    vi.restoreAllMocks()
  })

  it('debug logs with prefix in non-production', () => {
    process.env.NODE_ENV = 'development'
    const spy = vi.spyOn(console, 'debug').mockImplementation(() => {})
    const log = createLogger('Test')
    log.debug('hello')
    expect(spy).toHaveBeenCalledWith('[Test]', 'hello')
  })

  it('info logs with prefix in non-production', () => {
    process.env.NODE_ENV = 'development'
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {})
    const log = createLogger('Test')
    log.info('info message')
    expect(spy).toHaveBeenCalledWith('[Test]', 'info message')
  })

  it('warn logs with prefix always', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const log = createLogger('Test')
    log.warn('warning')
    expect(spy).toHaveBeenCalledWith('[Test]', 'warning')
  })

  it('error logs with prefix always', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const log = createLogger('Test')
    log.error('error msg')
    expect(spy).toHaveBeenCalledWith('[Test]', 'error msg')
  })

  it('warn with toast option triggers showEventToast', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const log = createLogger('Test')
    log.warn('warning toast', { toast: true })
    expect(showEventToastMock).toHaveBeenCalledWith('warning', 'warning toast')
  })

  it('error with toast option triggers showEventToast', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const log = createLogger('Test')
    log.error('error toast', { toast: true })
    expect(showEventToastMock).toHaveBeenCalledWith('error', 'error toast')
  })

  it('warn without toast option does not trigger showEventToast', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const log = createLogger('Test')
    log.warn('warning')
    expect(showEventToastMock).not.toHaveBeenCalled()
  })

  it('error without toast option does not trigger showEventToast', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const log = createLogger('Test')
    log.error('error')
    expect(showEventToastMock).not.toHaveBeenCalled()
  })
})

describe('useLogger', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('is an alias for createLogger', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const log = useLogger('Alias')
    log.error('test')
    expect(spy).toHaveBeenCalledWith('[Alias]', 'test')
  })

  it('createLogger and useLogger produce loggers with same behaviour', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const logA = createLogger('Same')
    const logB = useLogger('Same')

    logA.warn('msg-a')
    logB.warn('msg-b')

    expect(spy).toHaveBeenCalledWith('[Same]', 'msg-a')
    expect(spy).toHaveBeenCalledWith('[Same]', 'msg-b')
  })

  it('debug passes extra arguments through', () => {
    process.env.NODE_ENV = 'development'
    const spy = vi.spyOn(console, 'debug').mockImplementation(() => {})
    const log = createLogger('Multi')
    log.debug('first', 'second', { key: 'val' })
    expect(spy).toHaveBeenCalledWith('[Multi]', 'first', 'second', { key: 'val' })
  })

  it('info passes extra arguments through', () => {
    process.env.NODE_ENV = 'development'
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {})
    const log = createLogger('Multi')
    log.info('a', 42, [1, 2])
    expect(spy).toHaveBeenCalledWith('[Multi]', 'a', 42, [1, 2])
  })

  it('warn converts non-string message to string for toast', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const log = createLogger('Toast')
    const numericMsg = 42
    log.warn(numericMsg, { toast: true })
    expect(showEventToastMock).toHaveBeenCalledWith('warning', '42')
  })

  it('error converts non-string message to string for toast', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const log = createLogger('Toast')
    const objMsg = { code: 500 }
    log.error(objMsg, { toast: true })
    expect(showEventToastMock).toHaveBeenCalledWith('error', String(objMsg))
  })
})
