export interface ToggleSetting {
  display?: string
  value: boolean
}

export function clonePluginSettings<Settings>(settings: Settings): Settings {
  return JSON.parse(JSON.stringify(settings)) as Settings
}

export function toggleEnabledCheckboxSetting(item: ToggleSetting): boolean {
  if (item.display === 'disabled') return false
  item.value = !item.value
  return true
}

interface SerializedSettingsSaverOptions<Snapshot> {
  snapshot: () => Snapshot
  hasChanges: () => boolean
  persist: (snapshot: Snapshot) => Promise<unknown> | unknown
  accept: (snapshot: Snapshot) => void
  refresh: () => void
  onError: (error: unknown) => void
  defer?: (callback: () => void) => void
}

export function createSerializedSettingsSaver<Snapshot>(options: SerializedSettingsSaverOptions<Snapshot>) {
  const { snapshot, hasChanges, persist, accept, refresh, onError, defer } = options
  let saving = false
  let activePromise: Promise<void> | null = null
  const schedule = defer || queueMicrotask

  const requestSave = (): Promise<void> | null => {
    if (saving) return activePromise
    if (!hasChanges()) return Promise.resolve()

    saving = true
    const pending = snapshot()
    let succeeded = false
    activePromise = Promise.resolve()
      .then(() => persist(pending))
      .then(() => {
        succeeded = true
        accept(pending)
      })
      .catch((error) => onError(error))
      .finally(() => {
        saving = false
        activePromise = null
        const changedDuringSave = JSON.stringify(snapshot()) !== JSON.stringify(pending)
        if (changedDuringSave) schedule(requestSave)
        else if (succeeded) refresh()
      })
    return activePromise
  }

  return { requestSave }
}
