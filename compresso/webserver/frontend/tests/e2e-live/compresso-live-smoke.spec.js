import { expect, test } from '@playwright/test'

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

test('loads an empty approval queue from the real database', async ({ page }) => {
  const approvalResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/compresso/api/v2/approval/tasks'),
  )
  await page.goto('/compresso/ui/approval')

  await expect(page.getByTestId('approval-queue-page')).toBeVisible()
  const approvalResponse = await approvalResponsePromise
  expect(approvalResponse.status()).toBe(200)
  await expect(approvalResponse.json()).resolves.toMatchObject({ recordsFiltered: 0, results: [] })
})
