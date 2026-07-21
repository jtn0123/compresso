import type { ApiSchema } from './contracts'

export type LibraryResult = ApiSchema<'LibraryResults'>
export type LibraryConfig = ApiSchema<'SettingsLibraryConfig'>
export type LibraryConfigExchange = ApiSchema<'SettingsLibraryConfigReadAndWrite'>
export type LibraryConfigExport = ApiSchema<'SettingsLibraryPluginConfigExport'>
export type LibraryEnabledPluginContract = ApiSchema<'SettingsLibraryEnabledPlugin'>

export interface LibraryListItem {
  id: number
  name: string
  path: string
  enableRemoteOnly: boolean
  enableScanner: boolean
  enableInotify: boolean
  tags: string[]
  locked: boolean
}

// Declared explicitly rather than via Omit<contract>: the contract schema
// accepts unknown keys (additionalProperties), whose index signature would
// make Omit collapse the specific property types.
export interface LibraryEnabledPlugin {
  plugin_id: string
  name: string
  description: string
  icon: string
  has_config: boolean
  author?: string
  version?: string
  tags?: string
  library_id?: number | null
  settings?: Record<string, unknown>
}

export interface LibraryPageSettings {
  libraryPath: string
  enableLibraryScanner: boolean
  libraryScanSchedule: number
  libraryScanFollowSymlinks: boolean
  concurrentFileTesters: number
  runLibraryScanOnStart: boolean
  enableLibraryFileMonitor: boolean
  clearPendingTasksOnStart: boolean
  autoManageCompletedTasks: boolean
  compressCompletedTasksLogs: boolean
  maxAgeOfCompletedTasks: number
  alwaysKeepFailedTasks: boolean
  approvalRequired: boolean
  stagingPath: string
}

function toBooleanSetting(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value
  if (value === 'true') return true
  if (value === 'false') return false
  return fallback
}

function toNumberSetting(value: unknown, fallback: number): number {
  // Numeric inputs round-trip through settings storage as strings
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

// Field-by-field lenient parsing: a settings payload with unexpected or
// missing values must degrade to defaults, never reject the whole page.
// Fallbacks mirror the backend defaults in compresso/config.py.
export function parseLibraryPageSettings(settings: Record<string, unknown>): LibraryPageSettings {
  return {
    libraryPath: typeof settings.library_path === 'string' ? settings.library_path : '',
    enableLibraryScanner: toBooleanSetting(settings.enable_library_scanner, false),
    libraryScanSchedule: toNumberSetting(settings.schedule_full_scan_minutes, 1440),
    libraryScanFollowSymlinks: toBooleanSetting(settings.follow_symlinks, true),
    concurrentFileTesters: toNumberSetting(settings.concurrent_file_testers, 2),
    runLibraryScanOnStart: toBooleanSetting(settings.run_full_scan_on_start, false),
    // enable_inotify is a per-library setting and is not part of the global
    // settings/read payload; it only ever arrives as a default here.
    enableLibraryFileMonitor: toBooleanSetting(settings.enable_inotify, false),
    clearPendingTasksOnStart: toBooleanSetting(settings.clear_pending_tasks_on_restart, false),
    autoManageCompletedTasks: toBooleanSetting(settings.auto_manage_completed_tasks, false),
    compressCompletedTasksLogs: toBooleanSetting(settings.compress_completed_tasks_logs, false),
    maxAgeOfCompletedTasks: toNumberSetting(settings.max_age_of_completed_tasks, 91),
    alwaysKeepFailedTasks: toBooleanSetting(settings.always_keep_failed_tasks, true),
    approvalRequired: toBooleanSetting(settings.approval_required, false),
    stagingPath: typeof settings.staging_path === 'string' ? settings.staging_path : '',
  }
}

export function normalizeLibraryEnabledPlugin(plugin: LibraryEnabledPluginContract): LibraryEnabledPlugin {
  return {
    plugin_id: plugin.plugin_id,
    name: plugin.name ?? '',
    description: plugin.description ?? '',
    icon: plugin.icon ?? '',
    has_config: plugin.has_config ?? false,
    ...(plugin.author !== undefined ? { author: plugin.author } : {}),
    ...(plugin.version !== undefined ? { version: plugin.version } : {}),
    ...(plugin.tags !== undefined ? { tags: plugin.tags } : {}),
    ...(plugin.library_id !== undefined ? { library_id: plugin.library_id } : {}),
    ...(plugin.settings !== undefined ? { settings: plugin.settings } : {}),
  }
}
