import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import axios from 'axios'
import { usePreviewJob } from '../usePreviewJob'

vi.mock('axios', () => ({ default: { post: vi.fn() } }))

vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: vi.fn((version, endpoint) => `http://localhost/compresso/api/${version}/${endpoint}`),
}))

function makePreviewJob() {
  const notify = vi.fn()
  const t = vi.fn((key) => key)
  const job = usePreviewJob({ notify, t })
  return { notify, t, job }
}

describe('usePreviewJob', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    axios.post.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts a preview job and polls until complete', async () => {
    const { job } = makePreviewJob()
    axios.post.mockResolvedValueOnce({ data: { job_id: 'job-1' } })
    await job.startPreview({ sourcePath: '/media/movie.mkv', libraryId: 2 })

    expect(axios.post).toHaveBeenCalledWith(
      'http://localhost/compresso/api/v2/preview/create',
      expect.objectContaining({ source_path: '/media/movie.mkv', library_id: 2 }),
    )
    expect(job.previewLoading.value).toBe(true)

    axios.post.mockResolvedValueOnce({ data: { status: 'processing' } })
    await vi.advanceTimersByTimeAsync(2000)
    expect(job.previewActive.value).toBe(false)

    axios.post.mockResolvedValueOnce({
      data: { status: 'complete', source_url: '/a', encoded_url: '/b' },
    })
    await vi.advanceTimersByTimeAsync(2000)
    expect(job.previewActive.value).toBe(true)
    expect(job.previewLoading.value).toBe(false)
    expect(job.previewData.value).toMatchObject({ source_url: '/a', encoded_url: '/b' })
  })

  it('notifies and stops polling when the job fails', async () => {
    const { notify, job } = makePreviewJob()
    axios.post.mockResolvedValueOnce({ data: { job_id: 'job-2' } })
    await job.startPreview({ sourcePath: '/media/movie.mkv' })

    axios.post.mockResolvedValueOnce({ data: { status: 'failed', error: 'boom' } })
    await vi.advanceTimersByTimeAsync(2000)

    expect(job.previewLoading.value).toBe(false)
    expect(job.previewActive.value).toBe(false)
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ type: 'negative' }))

    // Polling must have stopped after the terminal status
    const callsAfterFailure = axios.post.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(axios.post.mock.calls.length).toBe(callsAfterFailure)
  })

  it('notifies when preview creation fails', async () => {
    const { notify, job } = makePreviewJob()
    axios.post.mockRejectedValueOnce(new Error('create failed'))
    await job.startPreview({ sourcePath: '/media/movie.mkv' })

    expect(job.previewLoading.value).toBe(false)
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ type: 'negative' }))
  })

  it('cleanupPreview stops polling, requests server cleanup, and resets state', async () => {
    const { job } = makePreviewJob()
    axios.post.mockResolvedValueOnce({ data: { job_id: 'job-3' } })
    await job.startPreview({ sourcePath: '/media/movie.mkv' })

    axios.post.mockResolvedValue({ data: { status: 'processing' } })
    await vi.advanceTimersByTimeAsync(2000)

    axios.post.mockClear()
    axios.post.mockResolvedValueOnce({ data: {} })
    await job.cleanupPreview()

    expect(axios.post).toHaveBeenCalledWith('http://localhost/compresso/api/v2/preview/cleanup', {
      job_id: 'job-3',
    })
    expect(job.previewActive.value).toBe(false)
    expect(job.previewLoading.value).toBe(false)
    expect(job.previewData.value).toBe(null)

    // No further polling after cleanup
    axios.post.mockClear()
    await vi.advanceTimersByTimeAsync(6000)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('cleanupPreview swallows server cleanup errors', async () => {
    const { job } = makePreviewJob()
    axios.post.mockResolvedValueOnce({ data: { job_id: 'job-4' } })
    await job.startPreview({ sourcePath: '/media/movie.mkv' })

    axios.post.mockRejectedValueOnce(new Error('cleanup failed'))
    await expect(job.cleanupPreview()).resolves.toBeUndefined()
    expect(job.previewActive.value).toBe(false)
  })

  it('resetPreviewState clears state without a server round trip', async () => {
    const { job } = makePreviewJob()
    job.previewActive.value = true
    job.previewLoading.value = true
    job.previewData.value = { source_url: '/x' }

    job.resetPreviewState()

    expect(job.previewActive.value).toBe(false)
    expect(job.previewLoading.value).toBe(false)
    expect(job.previewData.value).toBe(null)
    expect(axios.post).not.toHaveBeenCalled()
  })
})
