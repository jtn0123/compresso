import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock axios before importing the module under test
vi.mock('axios', () => ({
  default: vi.fn(),
}))

// Mock quasar's setCssVar and Notify
vi.mock('quasar', () => ({
  setCssVar: vi.fn(),
  Notify: { create: vi.fn() },
}))

import axios from 'axios'
import compressoGlobals, { notificationsCount } from '../compressoGlobals'

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
