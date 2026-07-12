import { expect, test } from '@playwright/test'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'

test('serves core API contracts from a fresh real backend', async ({ request }) => {
  const readinessResponse = await request.get('/compresso/api/v2/healthcheck/readiness')
  expect(readinessResponse.ok()).toBe(true)
  await expect(readinessResponse.json()).resolves.toMatchObject({ ready: true, success: true })

  const systemResponse = await request.get('/compresso/api/v2/system/status')
  expect(systemResponse.ok()).toBe(true)
  const system = await systemResponse.json()
  expect(Array.isArray(system.gpus)).toBe(true)
  for (const gpu of system.gpus) {
    expect(gpu).toEqual(expect.objectContaining({ hwaccel: expect.any(String), index: expect.any(Number) }))
  }

  const settingsResponse = await request.get('/compresso/api/v2/settings/read')
  expect(settingsResponse.ok()).toBe(true)
  const { settings } = await settingsResponse.json()
  expect(settings).toBeTruthy()
  expect(settings).not.toHaveProperty('api_auth_token')
})

test('loads the dashboard against the real API and websocket', async ({ page }) => {
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  const webSocketPromise = page.waitForEvent('websocket', (socket) => socket.url().endsWith('/compresso/websocket'))
  const systemResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/compresso/api/v2/system/status'),
  )
  await page.goto('/compresso/ui/dashboard')

  await expect(page.getByTestId('dashboard-page')).toBeVisible()
  const webSocket = await webSocketPromise
  const receivedFrames = []
  webSocket.on('framereceived', (event) => receivedFrames.push(event.payload))
  await expect.poll(() => receivedFrames.length).toBeGreaterThan(0)
  expect((await systemResponsePromise).status()).toBe(200)
  expect(pageErrors).toEqual([])
})

test('runs approval and rejection through the packaged backend and survives restart', async ({ page, request }) => {
  const homeDir = process.env.LIVE_E2E_HOME_DIR
  const fixtures = JSON.parse(readFileSync(path.join(homeDir, 'e2e-fixture.json'), 'utf8'))
  const approvalResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/compresso/api/v2/approval/tasks'),
  )
  await page.goto('/compresso/ui/approval')

  await expect(page.getByTestId('approval-queue-page')).toBeVisible()
  const approvalResponse = await approvalResponsePromise
  expect(approvalResponse.status()).toBe(200)
  await expect(approvalResponse.json()).resolves.toMatchObject({ recordsFiltered: 2 })

  const reject = await request.post('/compresso/api/v2/approval/reject', {
    data: { id_list: [fixtures.reject.id], requeue: false },
  })
  expect(reject.ok()).toBe(true)
  expect(readFileSync(fixtures.reject.source, 'utf8')).toBe('original-reject')
  expect(existsSync(fixtures.reject.staged_dir)).toBe(false)

  const approve = await request.post('/compresso/api/v2/approval/approve', {
    data: { id_list: [fixtures.approve.id] },
  })
  expect(approve.ok()).toBe(true)
  await expect.poll(() => readFileSync(fixtures.approve.source, 'utf8')).toBe('encoded-approve')
  await expect.poll(() => existsSync(fixtures.approve.staged_dir)).toBe(false)

  const historyCount = async () => {
    const response = await request.post('/compresso/api/v2/history/tasks', {
      data: { start: 0, length: 10, status: 'all', order_direction: 'desc' },
    })
    if (!response.ok()) return `HTTP ${response.status()}: ${await response.text()}`
    return (await response.json()).recordsFiltered
  }
  await expect.poll(historyCount).toBe(1)

  const oldPid = readFileSync(path.join(homeDir, 'backend.pid'), 'utf8')
  writeFileSync(path.join(homeDir, 'restart-requested'), 'restart')
  await expect.poll(() => readFileSync(path.join(homeDir, 'backend.pid'), 'utf8')).not.toBe(oldPid)
  await expect
    .poll(async () => {
      try {
        return (await request.get('/compresso/api/v2/healthcheck/readiness')).ok()
      } catch {
        return false
      }
    })
    .toBe(true)

  await expect.poll(historyCount).toBe(1)
})
