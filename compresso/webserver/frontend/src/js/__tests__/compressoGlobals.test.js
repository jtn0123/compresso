import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock axios before importing the module under test
vi.mock('axios', () => ({
  default: vi.fn(),
}))

// Mock quasar's setCssVar, Notify, and LocalStorage
const mockLocalStorageGetItem = vi.fn()
const mockLocalStorageSet = vi.fn()
vi.mock('quasar', () => ({
  setCssVar: vi.fn(),
  Notify: { create: vi.fn() },
  LocalStorage: {
    getItem: (...args) => mockLocalStorageGetItem(...args),
    set: (...args) => mockLocalStorageSet(...args),
  },
}))

// Mock compressoTheme so compressoGlobals.setTheme can be tested in isolation
const mockApplyTheme = vi.fn()
vi.mock('src/js/compressoTheme', () => ({
  applyTheme: (...args) => mockApplyTheme(...args),
}))

import axios from 'axios'
import { Notify } from 'quasar'
import compressoGlobals, {
  notificationsCount,
  toastSettings,
  showEventToast,
  saveToastSettings,
  setTheme,
} from '../compressoGlobals'

describe('notificationsCount', () => {
  beforeEach(() => {
    notificationsCount.value = 0
    // Reset internal notification list
    compressoGlobals.$compresso.notificationsList = undefined
  })

  it('starts at 0', () => {
    expect(notificationsCount.value).toBe(0)
  })
})

describe('getCompressoNotifications', () => {
  beforeEach(() => {
    compressoGlobals.$compresso.notificationsList = undefined
  })

  it('returns empty array by default', () => {
    const result = compressoGlobals.getCompressoNotifications()
    expect(result).toEqual([])
  })
})

describe('updateCompressoNotifications', () => {
  beforeEach(() => {
    notificationsCount.value = 0
    compressoGlobals.$compresso.notificationsList = undefined
    vi.clearAllMocks()
  })

  it('updates notificationsCount on success', async () => {
    const mockNotifications = [
      { uuid: '1', icon: 'info', navigation: '', label: 'test', message: 'msg', type: 'info' },
      { uuid: '2', icon: 'warning', navigation: '', label: 'test2', message: 'msg2', type: 'warning' },
    ]
    axios.mockResolvedValueOnce({
      data: { notifications: mockNotifications },
    })

    const $t = (key) => key

    await compressoGlobals.updateCompressoNotifications($t)
    expect(notificationsCount.value).toBe(2)
  })

  it('keeps notificationsCount unchanged on API failure', async () => {
    notificationsCount.value = 5
    axios.mockRejectedValueOnce(new Error('Network error'))

    const $t = (key) => key

    await compressoGlobals.updateCompressoNotifications($t)
    expect(notificationsCount.value).toBe(5)
  })
})

// ------------------------------------------------------------------
// Toast notifications
// ------------------------------------------------------------------

describe('toastSettings', () => {
  it('has enabled=true and verbosity=all by default', () => {
    expect(toastSettings.enabled).toBe(true)
    expect(toastSettings.verbosity).toBe('all')
  })
})

describe('showEventToast', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    toastSettings.enabled = true
    toastSettings.verbosity = 'all'
  })

  it('calls Notify.create for a success toast', () => {
    showEventToast('success', 'File completed')
    expect(Notify.create).toHaveBeenCalledTimes(1)
    const callArg = Notify.create.mock.calls[0][0]
    expect(callArg.color).toBe('positive')
    expect(callArg.message).toBe('File completed')
    expect(callArg.position).toBe('bottom-right')
  })

  it('calls Notify.create for an error toast', () => {
    showEventToast('error', 'Task failed')
    const callArg = Notify.create.mock.calls[0][0]
    expect(callArg.color).toBe('negative')
    expect(callArg.icon).toBe('error')
  })

  it('does not fire when enabled=false', () => {
    toastSettings.enabled = false
    showEventToast('success', 'Should not appear')
    expect(Notify.create).not.toHaveBeenCalled()
  })

  it('does not fire when verbosity=off', () => {
    toastSettings.verbosity = 'off'
    showEventToast('success', 'Should not appear')
    expect(Notify.create).not.toHaveBeenCalled()
  })

  it('filters success in important mode', () => {
    toastSettings.verbosity = 'important'
    showEventToast('success', 'Filtered out')
    expect(Notify.create).not.toHaveBeenCalled()
  })

  it('allows error in important mode', () => {
    toastSettings.verbosity = 'important'
    showEventToast('error', 'Should show')
    expect(Notify.create).toHaveBeenCalledTimes(1)
  })

  it('allows warning in important mode', () => {
    toastSettings.verbosity = 'important'
    showEventToast('warning', 'Should show')
    expect(Notify.create).toHaveBeenCalledTimes(1)
  })
})

describe('saveToastSettings', () => {
  it('persists to localStorage without throwing', () => {
    mockLocalStorageSet.mockClear()

    toastSettings.enabled = false
    toastSettings.verbosity = 'important'
    saveToastSettings()

    expect(mockLocalStorageSet).toHaveBeenCalledWith('compresso-toast-settings', {
      enabled: false,
      verbosity: 'important',
    })
  })
})

// ------------------------------------------------------------------
// setTheme (delegates to compressoTheme.applyTheme)
// ------------------------------------------------------------------

describe('setTheme', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLocalStorageGetItem.mockReturnValue(null)
  })

  it('calls applyTheme with mode and defaults palette to forest', () => {
    setTheme('dark')
    expect(mockApplyTheme).toHaveBeenCalledWith('dark', 'forest')
  })

  it('passes stored palette from localStorage', () => {
    mockLocalStorageGetItem.mockReturnValue('ember')
    setTheme('light')
    expect(mockApplyTheme).toHaveBeenCalledWith('light', 'ember')
  })

  it('reads palette key from LocalStorage', () => {
    setTheme('dark')
    expect(mockLocalStorageGetItem).toHaveBeenCalledWith('palette')
  })
})
