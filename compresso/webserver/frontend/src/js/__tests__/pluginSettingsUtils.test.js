import { describe, expect, it, vi } from 'vitest'
import {
  clonePluginSettings,
  createSerializedSettingsSaver,
  toggleEnabledCheckboxSetting,
} from '../pluginSettingsUtils'

describe('plugin settings utilities', () => {
  it('does not toggle a disabled checkbox setting', () => {
    const item = { display: 'disabled', value: false }

    expect(toggleEnabledCheckboxSetting(item)).toBe(false)
    expect(item.value).toBe(false)
  })

  it('queues the latest edit made while a save is active', async () => {
    let settings = [{ key_id: 'quality', value: 1 }]
    let accepted = [{ key_id: 'quality', value: 0 }]
    const pendingRequests = []
    const refresh = vi.fn()
    const saver = createSerializedSettingsSaver({
      snapshot: () => clonePluginSettings(settings),
      hasChanges: () => settings[0].value !== accepted[0].value,
      persist: (snapshot) =>
        new Promise((resolve) => {
          pendingRequests.push({ snapshot, resolve })
        }),
      accept: (snapshot) => {
        accepted = snapshot
      },
      refresh,
      onError: vi.fn(),
      defer: queueMicrotask,
    })

    const firstSave = saver.requestSave()
    await Promise.resolve()
    settings = [{ key_id: 'quality', value: 2 }]
    saver.requestSave()
    expect(pendingRequests).toHaveLength(1)
    expect(pendingRequests[0].snapshot[0].value).toBe(1)

    pendingRequests[0].resolve()
    await firstSave
    await Promise.resolve()
    await Promise.resolve()

    expect(pendingRequests).toHaveLength(2)
    expect(pendingRequests[1].snapshot[0].value).toBe(2)
    expect(refresh).not.toHaveBeenCalled()

    const secondSave = saver.requestSave()
    pendingRequests[1].resolve()
    await secondSave
    expect(refresh).toHaveBeenCalledOnce()
  })

  it('reports a failed save without retrying the unchanged snapshot forever', async () => {
    const settings = [{ key_id: 'quality', value: 1 }]
    const persist = vi.fn().mockRejectedValue(new Error('offline'))
    const onError = vi.fn()
    const saver = createSerializedSettingsSaver({
      snapshot: () => clonePluginSettings(settings),
      hasChanges: () => true,
      persist,
      accept: vi.fn(),
      refresh: vi.fn(),
      onError,
      defer: queueMicrotask,
    })

    await saver.requestSave()
    await Promise.resolve()

    expect(persist).toHaveBeenCalledOnce()
    expect(onError).toHaveBeenCalledOnce()
  })
})
