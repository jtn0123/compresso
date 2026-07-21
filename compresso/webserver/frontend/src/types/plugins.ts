import type { ApiSchema } from './contracts'

export type PluginStatus = ApiSchema<'PluginStatus'>
export type PluginTableResult = ApiSchema<'PluginsTableResults'>
export type PluginInfoResult = ApiSchema<'PluginsInfoResults'>
export type PluginFlowEntry = ApiSchema<'PluginFlowDataResults'>
export type PluginRepo = ApiSchema<'PluginReposMetadataResults'>
export type InstallablePluginContract = ApiSchema<'PluginsMetadataInstallableResults'>
export type SelectablePlugin = Omit<Pick<
  PluginTableResult,
  'plugin_id' | 'name' | 'author' | 'description' | 'version' | 'icon' | 'tags' | 'has_config'
>, 'has_config'> & { has_config: boolean }
export type PluginSettingValue = string | number | boolean | null

export interface PluginSelectOption {
  label: string
  value: PluginSettingValue
}

export interface PluginSliderOptions {
  min: number | string | undefined
  max: number | string | undefined
  step: number | string | undefined
  suffix: string | undefined
}

/** UI-normalized form of the generated plugin setting contract. */
interface PluginSettingBase {
  key_id: string
  key: string
  label: string
  description: string
  tooltip: string | null
  select_options: PluginSelectOption[]
  slider_options: PluginSliderOptions
  display: string
  sub_setting: boolean
}

export type PluginSetting = PluginSettingBase & (
  | { input_type: 'text' | 'textarea' | 'browse_directory'; value: string }
  | { input_type: 'checkbox'; value: boolean }
  | { input_type: 'slider'; value: number }
  | { input_type: 'select'; value: PluginSettingValue }
  | {
      input_type: 'section_header' | 'section_subheader' | 'section_details' | 'section_admonition'
      value: PluginSettingValue
    }
  | { input_type: 'unknown'; value: PluginSettingValue }
)

export interface InstalledPlugin extends Omit<PluginTableResult, 'description' | 'has_config'> {
  description: string
  has_config: boolean
}

export interface PaginationState {
  sortBy: string
  descending: boolean
  page: number
  rowsPerPage: number
  rowsNumber: number
}

export interface TableRequest {
  pagination: PaginationState
  filter?: string | undefined
}

export interface CommunityRepo {
  id: string
  name: string
  author: string
  owner_avatar: string
  icon: string
  description: string
  stars: number
  pushed_at: string | undefined
  pushed_at_formatted: string
  html_url: string
  repo_token: string | undefined
  repo_json_url: string
}

export interface PluginFlowType {
  type: string
  labelCode: string
}

export interface InstallablePlugin
  extends Omit<InstallablePluginContract, 'status' | 'repo_id' | 'repo_name' | 'package_url' | 'changelog_url'> {
  installed: boolean
  update_available: boolean
  repo_id: string
  repo_name: string
  package_url: string
  changelog_url: string
}

export function normalizeInstallablePlugin(plugin: InstallablePluginContract): InstallablePlugin | null {
  if (!plugin.repo_id) return null
  return {
    plugin_id: plugin.plugin_id,
    name: plugin.name,
    author: plugin.author,
    description: plugin.description,
    version: plugin.version,
    icon: plugin.icon,
    tags: plugin.tags,
    installed: plugin.status.installed ?? false,
    update_available: plugin.status.update_available ?? false,
    repo_id: plugin.repo_id,
    repo_name: plugin.repo_name ?? '',
    package_url: plugin.package_url ?? '',
    changelog_url: plugin.changelog_url ?? '',
  }
}

export function normalizePluginSetting(input: ApiSchema<'PluginsConfigInputItem'>): PluginSetting {
  const normalizeValue = (value: unknown): PluginSettingValue =>
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean' ||
    value === null
      ? value
      : String(value ?? '')

  const base: PluginSettingBase = {
    key_id: input.key_id,
    key: input.key,
    label: input.label,
    description: input.description ?? '',
    tooltip: input.tooltip ?? null,
    select_options: input.select_options.map((option) => ({
      label: typeof option.label === 'string' ? option.label : String(option.label ?? ''),
      value: normalizeValue(option.value),
    })),
    slider_options: {
      min: typeof input.slider_options.min === 'number' || typeof input.slider_options.min === 'string'
        ? input.slider_options.min
        : undefined,
      max: typeof input.slider_options.max === 'number' || typeof input.slider_options.max === 'string'
        ? input.slider_options.max
        : undefined,
      step: typeof input.slider_options.step === 'number' || typeof input.slider_options.step === 'string'
        ? input.slider_options.step
        : undefined,
      suffix: typeof input.slider_options.suffix === 'string' ? input.slider_options.suffix : undefined,
    },
    display: input.display,
    sub_setting: input.sub_setting,
  }

  switch (input.input_type) {
    case 'text':
    case 'textarea':
    case 'browse_directory':
      return { ...base, input_type: input.input_type, value: String(input.value ?? '') }
    case 'checkbox':
      return { ...base, input_type: input.input_type, value: Boolean(input.value) }
    case 'slider': {
      const numericValue = typeof input.value === 'number' ? input.value : Number(input.value)
      return { ...base, input_type: input.input_type, value: Number.isFinite(numericValue) ? numericValue : 0 }
    }
    case 'select':
      return { ...base, input_type: input.input_type, value: normalizeValue(input.value) }
    default:
      if (
        input.input_type === 'section_header' ||
        input.input_type === 'section_subheader' ||
        input.input_type === 'section_details' ||
        input.input_type === 'section_admonition'
      ) {
        return { ...base, input_type: input.input_type, value: normalizeValue(input.value) }
      }
      return { ...base, input_type: 'unknown', value: normalizeValue(input.value) }
  }
}
