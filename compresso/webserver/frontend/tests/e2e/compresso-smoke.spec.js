import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const runtimeErrorsByPage = new WeakMap()

const approvalTasks = [
  {
    id: 101,
    abspath: '/media/movies/Big Buck Bunny.mkv',
    source_codec: 'h264',
    staged_codec: 'hevc',
    source_size: 1000000,
    staged_size: 640000,
    size_delta: -360000,
    vmaf_score: 94.2,
    ssim_score: 0.98,
    finish_time: '2026-07-07 09:00:00',
    source_resolution: '1920x1080',
    staged_resolution: '1920x1080',
  },
  {
    id: 102,
    abspath: '/media/tv/Pilot.mp4',
    source_codec: 'h264',
    staged_codec: 'h264',
    source_size: 1500000,
    staged_size: 1000000,
    size_delta: -500000,
    vmaf_score: 88.4,
    ssim_score: 0.96,
    finish_time: '2026-07-07 10:00:00',
    source_resolution: '1280x720',
    staged_resolution: '1280x720',
  },
]

const pendingTasks = [
  {
    id: 201,
    abspath: '/media/inbox/Pending Movie.mkv',
    library_name: 'Movies',
  },
]

const completedTasks = [
  {
    id: 301,
    task_label: '/media/done/Completed Movie.mkv',
    finish_time: '2026-07-07 11:00:00',
    task_success: true,
    has_metadata: true,
  },
]

function json(body) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

async function installApiMocks(page, requests = [], options = {}) {
  let onboardingCompleted = options.onboardingCompleted ?? true
  await page.route('https://api.github.com/repos/jtn0123/compresso/releases/tags/*', (route) =>
    route.fulfill(json({ tag_name: '0.0.0-e2e', body: 'Mock release notes' })),
  )
  await page.route('**/compresso/api/v2/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const endpoint = url.pathname.split('/compresso/api/v2/')[1]
    let payload = null
    try {
      payload = request.postDataJSON()
    } catch {
      payload = null
    }
    requests.push({ endpoint, method: request.method(), payload })

    if (endpoint === 'version/read') {
      return route.fulfill(json({ version: '0.0.0-e2e' }))
    }
    if (endpoint === 'settings/read') {
      return route.fulfill(
        json({
          settings: {
            onboarding_completed: onboardingCompleted,
            approval_required: true,
            release_notes_viewed: '0.0.0-e2e',
            libraries: [{ id: 1, name: 'Movies' }],
            remote_installations: [],
          },
        }),
      )
    }
    if (endpoint === 'settings/libraries') {
      return route.fulfill(json({ libraries: [{ id: 1, name: 'Movies' }] }))
    }
    if (endpoint === 'settings/worker_groups') {
      return route.fulfill(json({ worker_groups: [] }))
    }
    if (endpoint === 'notifications/read') {
      return route.fulfill(json({ notifications: [] }))
    }
    if (endpoint === 'plugins/panels/enabled') {
      return route.fulfill(json({ results: [] }))
    }
    if (endpoint === 'plugins/installed') {
      return route.fulfill(json({ recordsFiltered: 0, results: [] }))
    }
    if (endpoint === 'plugins/installable') {
      return route.fulfill(json({ plugins: [] }))
    }
    if (endpoint === 'plugins/repos/list') {
      return route.fulfill(
        json({
          repos: [
            {
              id: 'official',
              name: 'Official plugins',
              icon: '',
              path: 'https://github.com/jtn0123/compresso-plugins',
              repo_html_url: 'https://github.com/jtn0123/compresso-plugins',
            },
          ],
        }),
      )
    }
    if (endpoint === 'settings/write') {
      onboardingCompleted = true
      return route.fulfill(json({ success: true }))
    }
    if (endpoint === 'system/status') {
      return route.fulfill(
        json({
          cpu: { percent: 8 },
          memory: { percent: 34, used_gb: 4 },
          disk: { percent: 55, used_gb: 120 },
          gpus: [],
        }),
      )
    }
    if (endpoint === 'system/safety') {
      return route.fulfill(json({ pause_required: true, status: 'paused', events: [] }))
    }
    if (endpoint === 'system/readiness') {
      return route.fulfill(
        json({
          ready: false,
          doctor_report_expired: false,
          doctor_report: {
            overall_status: 'pass',
            generated_at: '2026-07-12T12:00:00Z',
            expires_at: '2026-07-13T12:00:00Z',
            checks: [{ id: 'cache', status: 'pass', summary: 'Cache is writable' }],
          },
          safety: {
            pause_required: true,
            events: [
              {
                id: 'event-1',
                code: 'disk-reserve',
                message: 'Cache reserve breached',
                active: true,
                acknowledged_at: null,
                first_seen_at: '2026-07-12T12:10:00Z',
              },
            ],
          },
        }),
      )
    }
    if (endpoint === 'system/safety/acknowledge' || endpoint === 'system/safety/resume') {
      return route.fulfill(json({ pause_required: false, status: 'ready', events: [] }))
    }
    if (endpoint === 'compression/optimization-progress') {
      return route.fulfill(json({ total: 10, processed: 4, percent: 40 }))
    }
    if (endpoint === 'compression/summary') {
      return route.fulfill(json({ total_space_saved: 860000, completed_count: 2, failed_count: 0 }))
    }
    if (endpoint === 'compression/pending-estimate') {
      return route.fulfill(json({ count: pendingTasks.length, estimated_size: 1200000, estimated_savings: 300000 }))
    }
    if (endpoint === 'healthcheck/summary') {
      return route.fulfill(json({ healthy: 8, warning: 1, corrupted: 0, scanning: false, scan_progress: {} }))
    }
    if (endpoint === 'healthcheck/workers') {
      return route.fulfill(json({ worker_count: 1 }))
    }
    if (endpoint === 'approval/count') {
      return route.fulfill(json({ count: approvalTasks.length }))
    }
    if (endpoint === 'approval/summary') {
      return route.fulfill(
        json({
          total_count: approvalTasks.length,
          total_source_size: 2500000,
          total_staged_size: 1640000,
          total_space_saved: 860000,
          average_savings_percent: 36.6,
          largest_savings_file: approvalTasks[1].abspath,
          largest_savings_bytes: 500000,
          average_vmaf: 91.3,
          codec_options: ['h264', 'hevc'],
        }),
      )
    }
    if (endpoint === 'approval/tasks') {
      return route.fulfill(json({ recordsFiltered: approvalTasks.length, results: approvalTasks }))
    }
    if (endpoint === 'approval/detail') {
      return route.fulfill(json({ ...approvalTasks[0], log: 'ffmpeg complete', start_time: '09:00', size_ratio: 0.64 }))
    }
    if (endpoint === 'approval/approve' || endpoint === 'approval/reject') {
      return route.fulfill(json({ success: true }))
    }
    if (endpoint === 'preview/create') {
      return route.fulfill(json({ job_id: 'preview-1' }))
    }
    if (endpoint === 'preview/status') {
      return route.fulfill(
        json({
          status: 'complete',
          source_url: 'data:video/mp4;base64,',
          encoded_url: 'data:video/mp4;base64,',
          source_size: 1000000,
          encoded_size: 640000,
          source_codec: 'h264',
          encoded_codec: 'hevc',
          vmaf_score: 94.2,
          ssim_score: 0.98,
        }),
      )
    }
    if (endpoint === 'pending/tasks') {
      return route.fulfill(json({ recordsFiltered: pendingTasks.length, results: pendingTasks }))
    }
    if (endpoint === 'history/tasks') {
      return route.fulfill(json({ recordsFiltered: completedTasks.length, results: completedTasks }))
    }
    if (endpoint === 'metadata/search') {
      return route.fulfill(json({ recordsFiltered: 0, results: [] }))
    }

    throw new Error(`Unhandled API mock: ${request.method()} ${endpoint}`)
  })
}

test.beforeEach(async ({ page }) => {
  const runtimeErrors = []
  runtimeErrorsByPage.set(page, runtimeErrors)
  await page.addInitScript(() => {
    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      constructor(url) {
        this.url = url
        this.readyState = MockWebSocket.OPEN
        this.listeners = {}
        setTimeout(() => this.dispatch('open'), 0)
      }

      addEventListener(type, callback) {
        this.listeners[type] = this.listeners[type] || new Set()
        this.listeners[type].add(callback)
      }

      removeEventListener(type, callback) {
        this.listeners[type]?.delete(callback)
      }

      dispatch(type, payload = {}) {
        const event = { type, target: this, ...payload }
        this[`on${type}`]?.(event)
        this.listeners[type]?.forEach((callback) => callback(event))
      }

      send() {}

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.dispatch('close')
      }
    }

    window.WebSocket = MockWebSocket
  })

  page.on('pageerror', (error) => {
    // WebKit reports this observer scheduling diagnostic as a page error even
    // though the browser recovers without losing layout or interaction state.
    if (error.message === 'ResizeObserver loop completed with undelivered notifications.') return
    runtimeErrors.push(`pageerror: ${error.message}`)
  })
  page.on('requestfailed', (request) =>
    runtimeErrors.push(
      `requestfailed: ${request.method()} ${request.url()} (${request.failure()?.errorText || 'unknown'})`,
    ),
  )
  page.on('response', (response) => {
    if (response.url().includes('/compresso/api/v2/') && response.status() >= 400) {
      runtimeErrors.push(`response: ${response.status()} ${response.request().method()} ${response.url()}`)
    }
  })
  page.on('console', (message) => {
    if (message.type() === 'error') {
      const source = message.location().url
      runtimeErrors.push(`console: ${message.text()}${source ? ` (${source})` : ''}`)
    }
  })
})

test.afterEach(async ({ page }) => {
  expect(runtimeErrorsByPage.get(page) || []).toEqual([])
})

test('loads the dashboard and opens pending/completed task dialogs @cross-browser', async ({ page }) => {
  await installApiMocks(page)

  await page.goto('/compresso/ui/dashboard')

  await expect(page.getByTestId('dashboard-page')).toBeVisible()
  await expect(page.getByText('Pending Tasks', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Completed Tasks', { exact: true }).first()).toBeVisible()

  await page.getByTestId('pending-tasks-open').click()
  await expect(page.getByRole('dialog').getByText('Pending Tasks')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog').getByText('Pending Tasks')).toBeHidden()

  await page.getByTestId('completed-tasks-open').click()
  await expect(page.getByRole('dialog').getByText('Completed Tasks')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog').getByText('Completed Tasks')).toBeHidden()
})

test('sends approval search filters and approve/reject requests', async ({ page }) => {
  const requests = []
  await installApiMocks(page, requests)

  await page.goto('/compresso/ui/approval')

  await expect(page.getByTestId('approval-queue-page')).toBeVisible()
  await expect(page.getByText('Big Buck Bunny.mkv', { exact: true }).first()).toBeVisible()

  await page.getByPlaceholder('Search').fill('Bunny')
  await expect
    .poll(() => requests.filter((entry) => entry.endpoint === 'approval/tasks').at(-1)?.payload?.search_value)
    .toBe('Bunny')

  const approveButton = page.getByRole('button', { name: /^Approve$/ }).first()
  await approveButton.focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => requests.some((entry) => entry.endpoint === 'approval/approve')).toBe(true)

  await page
    .getByRole('button', { name: /^Reject$/ })
    .first()
    .click()
  await expect(page.getByText('What happens to rejected files?')).toBeVisible()
  await page
    .getByRole('button', { name: /^Reject$/ })
    .last()
    .click()
  await expect.poll(() => requests.some((entry) => entry.endpoint === 'approval/reject')).toBe(true)
})

test('opens approval detail and starts the compare preview', async ({ page }) => {
  await installApiMocks(page)

  await page.goto('/compresso/ui/approval')

  await page.getByRole('button', { name: 'Details' }).first().click()
  await expect(page.getByRole('dialog').getByText('Big Buck Bunny.mkv', { exact: true }).first()).toBeVisible()

  await page.getByTestId('approval-compare-quality').click()
  await expect(page.getByRole('button', { name: 'Side by Side' })).toBeVisible()
  await expect(page.getByRole('dialog').getByText('VMAF: 94.2').first()).toBeVisible()
})

test('onboarding and plugin controls stay usable on narrow keyboard layouts @mobile @accessibility', async ({
  page,
}) => {
  await installApiMocks(page, [], { onboardingCompleted: false })

  await page.goto('/compresso/ui/dashboard')

  const onboarding = page.getByRole('dialog')
  await expect(onboarding.getByText('Welcome to Compresso')).toBeVisible()
  const dialogBounds = await onboarding.boundingBox()
  expect(dialogBounds.width).toBeLessThanOrEqual(page.viewportSize().width)

  const accessibility = await new AxeBuilder({ page }).include('.first-run-card').analyze()
  expect(accessibility.violations.filter((violation) => ['critical', 'serious'].includes(violation.impact))).toEqual([])

  await onboarding.getByRole('textbox').fill('/media/library')
  for (let step = 0; step < 2; step += 1) {
    const nextButton = onboarding.getByRole('button', { name: 'Next' })
    await nextButton.focus()
    await page.keyboard.press('Enter')
  }
  const finishButton = onboarding.getByRole('button', { name: 'Finish Setup' })
  await finishButton.focus()
  await page.keyboard.press('Enter')
  await expect(onboarding).toBeHidden()

  await page.goto('/compresso/ui/settings-plugins')
  await page.getByRole('button', { name: 'Install Plugin From Repo' }).click()
  await expect(page.getByRole('dialog').getByText('Plugin Installer')).toBeVisible()
  await page.getByRole('button', { name: 'Repository List' }).click()

  const repoLink = page.getByRole('link', { name: 'https://github.com/jtn0123/compresso-plugins' }).first()
  await repoLink.focus()
  await expect(repoLink).toBeFocused()
  await expect(repoLink).toHaveAttribute('href', 'https://github.com/jtn0123/compresso-plugins')
})

test('reviews and operates the durable deployment safety gate @cross-browser @mobile', async ({ page }) => {
  const requests = []
  await installApiMocks(page, requests)

  await page.goto('/compresso/ui/readiness')

  await expect(page.getByText('Deployment gate is closed')).toBeVisible()
  await expect(page.getByText('Cache reserve breached')).toBeVisible()
  await expect(page.getByText('Cache is writable')).toBeVisible()

  await page.getByTestId('acknowledge-event-1').click()
  await expect.poll(() => requests.some((entry) => entry.endpoint === 'system/safety/acknowledge')).toBe(true)

  await page.getByTestId('resume-workers').click()
  await expect.poll(() => requests.some((entry) => entry.endpoint === 'system/safety/resume')).toBe(true)
})
