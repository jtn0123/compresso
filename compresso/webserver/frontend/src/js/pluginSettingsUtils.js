export function clonePluginSettings(settings) {
  return JSON.parse(JSON.stringify(settings))
}

export function toggleEnabledCheckboxSetting(item) {
  if (item.display === 'disabled') return false
  item.value = !item.value
  return true
}

export function createSerializedSettingsSaver({ snapshot, hasChanges, persist, accept, refresh, onError, defer }) {
  let saving = false
  let activePromise = null
  const schedule = defer || queueMicrotask

  const requestSave = () => {
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
