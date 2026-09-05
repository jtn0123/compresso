import { describe, expect, it } from 'vitest'
import { normalizeLibraryEnabledPlugin, parseLibraryPageSettings } from '../libraries'

// A realistic settings/read payload: global config keys only. Note that
// enable_inotify is a per-library setting and is never present here.
const REAL_SETTINGS_PAYLOAD: Record<string, unknown> = {
  library_path: '/library',
  enable_library_scanner: true,
  schedule_full_scan_minutes: 60,
  follow_symlinks: true,
  concurrent_file_testers: 3,
  run_full_scan_on_start: false,
  clear_pending_tasks_on_restart: false,
  auto_manage_completed_tasks: true,
  compress_completed_tasks_logs: false,
  max_age_of_completed_tasks: 30,
  always_keep_failed_tasks: true,
  approval_required: 'false',
  staging_path: '/staging',
}

describe('parseLibraryPageSettings', () => {
  it('parses the real settings/read payload (no enable_inotify key)', () => {
    const settings = parseLibraryPageSettings(REAL_SETTINGS_PAYLOAD)

    expect(settings.libraryPath).toBe('/library')
    expect(settings.enableLibraryScanner).toBe(true)
    expect(settings.libraryScanSchedule).toBe(60)
    expect(settings.concurrentFileTesters).toBe(3)
    expect(settings.enableLibraryFileMonitor).toBe(false)
    expect(settings.maxAgeOfCompletedTasks).toBe(30)
    expect(settings.approvalRequired).toBe(false)
    expect(settings.stagingPath).toBe('/staging')
  })

  it('coerces numeric strings the way settings storage round-trips them', () => {
    const settings = parseLibraryPageSettings({
      ...REAL_SETTINGS_PAYLOAD,
      schedule_full_scan_minutes: '120',
      max_age_of_completed_tasks: '45',
    })

    expect(settings.libraryScanSchedule).toBe(120)
    expect(settings.maxAgeOfCompletedTasks).toBe(45)
  })

  it('degrades per-field to backend defaults instead of rejecting the page', () => {
    const settings = parseLibraryPageSettings({})

    expect(settings.libraryPath).toBe('')
    expect(settings.enableLibraryScanner).toBe(false)
    expect(settings.libraryScanSchedule).toBe(1440)
    expect(settings.libraryScanFollowSymlinks).toBe(true)
    expect(settings.concurrentFileTesters).toBe(2)
    expect(settings.maxAgeOfCompletedTasks).toBe(91)
    expect(settings.alwaysKeepFailedTasks).toBe(true)
    expect(settings.approvalRequired).toBe(false)
  })

  it('ignores garbage values without failing the whole payload', () => {
    const settings = parseLibraryPageSettings({
      ...REAL_SETTINGS_PAYLOAD,
      schedule_full_scan_minutes: 'not-a-number',
      enable_library_scanner: 42,
    })

    expect(settings.libraryScanSchedule).toBe(1440)
    expect(settings.enableLibraryScanner).toBe(false)
    expect(settings.libraryPath).toBe('/library')
  })
})

describe('normalizeLibraryEnabledPlugin', () => {
  it('fills display defaults and keeps optional export fields', () => {
    const plugin = normalizeLibraryEnabledPlugin({
      plugin_id: 'notify_plex',
      library_id: 1,
      settings: { notify_on_failure: true },
    })

    expect(plugin.plugin_id).toBe('notify_plex')
    expect(plugin.name).toBe('')
    expect(plugin.has_config).toBe(false)
    expect(plugin.library_id).toBe(1)
    expect(plugin.settings).toEqual({ notify_on_failure: true })
  })
})
