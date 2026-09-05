import type { QNotifyCreateOptions } from 'quasar'
import type { Composer } from 'vue-i18n'

export type Translate = Composer['t']
export type Notify = (options: QNotifyCreateOptions) => unknown

export interface DialogAction {
  emit?: string
  label?: string
  icon?: string
  color?: string
  disabled?: boolean
  tooltip?: string
}

export interface DialogController {
  show(): void
  hide(): void
}
