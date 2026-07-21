/** Runtime identity helpers for Quasar's build-time-only #q-app test alias. */
export function defineBoot<Callback>(callback: Callback): Callback {
  return callback
}
