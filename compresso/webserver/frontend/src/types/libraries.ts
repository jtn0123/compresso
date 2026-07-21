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

export interface LibraryEnabledPlugin
  extends Omit<LibraryEnabledPluginContract, 'description' | 'icon' | 'has_config'> {
  description: string
  icon: string
  has_config: boolean
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

function isBooleanSetting(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

export function parseLibraryPageSettings(settings: Record<string, unknown>): LibraryPageSettings | null {
  const approvalRequired =
    isBooleanSetting(settings.approval_required)
      ? settings.approval_required
      : settings.approval_required === 'true'
        ? true
        : settings.approval_required === 'false'
          ? false
          : null
  if (
    typeof settings.library_path !== 'string' ||
    !isBooleanSetting(settings.enable_library_scanner) ||
    typeof settings.schedule_full_scan_minutes !== 'number' ||
    !isBooleanSetting(settings.follow_symlinks) ||
    typeof settings.concurrent_file_testers !== 'number' ||
    !isBooleanSetting(settings.run_full_scan_on_start) ||
    !isBooleanSetting(settings.enable_inotify) ||
    !isBooleanSetting(settings.clear_pending_tasks_on_restart) ||
    !isBooleanSetting(settings.auto_manage_completed_tasks) ||
    !isBooleanSetting(settings.compress_completed_tasks_logs) ||
    typeof settings.max_age_of_completed_tasks !== 'number' ||
    !isBooleanSetting(settings.always_keep_failed_tasks) ||
    approvalRequired === null ||
    (settings.staging_path != null && typeof settings.staging_path !== 'string')
  ) {
    return null
  }
  return {
    libraryPath: settings.library_path,
    enableLibraryScanner: settings.enable_library_scanner,
    libraryScanSchedule: settings.schedule_full_scan_minutes,
    libraryScanFollowSymlinks: settings.follow_symlinks,
    concurrentFileTesters: settings.concurrent_file_testers,
    runLibraryScanOnStart: settings.run_full_scan_on_start,
    enableLibraryFileMonitor: settings.enable_inotify,
    clearPendingTasksOnStart: settings.clear_pending_tasks_on_restart,
    autoManageCompletedTasks: settings.auto_manage_completed_tasks,
    compressCompletedTasksLogs: settings.compress_completed_tasks_logs,
    maxAgeOfCompletedTasks: settings.max_age_of_completed_tasks,
    alwaysKeepFailedTasks: settings.always_keep_failed_tasks,
    approvalRequired,
    stagingPath: settings.staging_path ?? '',
  }
}

export function normalizeLibraryEnabledPlugin(plugin: LibraryEnabledPluginContract): LibraryEnabledPlugin {
  return {
    ...plugin,
    description: plugin.description ?? '',
    icon: plugin.icon ?? '',
    has_config: plugin.has_config ?? false,
  }
}
