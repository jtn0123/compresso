import { ref } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { createLogger } from 'src/composables/useLogger'
import type { ApiSchema } from 'src/types/contracts'
import type { Notify, Translate } from 'src/types/ui'

const log = createLogger('usePreviewJob')

/**
 * Manage a server-side preview transcode job: creation, status polling, and
 * cleanup. Extracted from ApprovalQueue.vue so pages/dialogs that offer a
 * side-by-side preview can share one implementation.
 *
 * @param {Object} options
 * @param {Function} options.notify Quasar `$q.notify`
 * @param {Function} options.t i18n translate function
 * @returns preview state refs and the start/cleanup actions
 */
interface PreviewJobOptions {
  notify: Notify
  t: Translate
}

interface StartPreviewOptions {
  sourcePath: string
  libraryId?: number
  startTime?: number
  duration?: number
}

export function usePreviewJob({ notify, t }: PreviewJobOptions) {
  const previewActive = ref(false)
  const previewLoading = ref(false)
  const previewStatus = ref('')
  const previewData = ref<ApiSchema<'PreviewStatusResponse'> | null>(null)
  let previewJobId: string | null = null
  let previewPollInterval: ReturnType<typeof setInterval> | null = null

  function stopPolling(): void {
    if (previewPollInterval !== null) clearInterval(previewPollInterval)
    previewPollInterval = null
  }

  function resetPreviewState(): void {
    previewActive.value = false
    previewLoading.value = false
    previewData.value = null
  }

  function pollPreviewStatus(): void {
    previewPollInterval = setInterval(async () => {
      try {
        const res = await axios.post<ApiSchema<'PreviewStatusResponse'>>(getCompressoApiUrl('v2', 'preview/status'), {
          job_id: previewJobId,
        })
        const status = res.data.status ?? ''
        previewStatus.value = status
        if (status === 'complete') {
          stopPolling()
          previewData.value = res.data
          previewLoading.value = false
          previewActive.value = true
        } else if (status === 'error' || status === 'failed') {
          stopPolling()
          previewLoading.value = false
          notify({
            type: 'negative',
            message: t('pages.approvalQueue.previewFailed', { error: res.data.error || '' }),
            timeout: 3000,
            position: 'top',
          })
        }
      } catch (err) {
        log.error('Preview status poll failed', err)
        stopPolling()
        previewLoading.value = false
      }
    }, 2000)
  }

  /**
   * Kick off a preview job for the given source file.
   *
   * @param {Object} params
   * @param {string} params.sourcePath Absolute path of the source media file
   * @param {number} [params.libraryId] Library the file belongs to
   * @param {number} [params.startTime] Clip start offset in seconds
   * @param {number} [params.duration] Clip duration in seconds
   */
  async function startPreview({ sourcePath, libraryId = 1, startTime = 0, duration = 10 }: StartPreviewOptions) {
    previewLoading.value = true
    previewStatus.value = t('pages.approvalQueue.previewStarting')
    try {
      const res = await axios.post<ApiSchema<'PreviewCreateResponse'>>(getCompressoApiUrl('v2', 'preview/create'), {
        source_path: sourcePath,
        start_time: startTime,
        duration: duration,
        library_id: libraryId,
      })
      if (!res.data.job_id) throw new Error('Preview response did not include a job ID')
      previewJobId = res.data.job_id
      previewStatus.value = t('pages.approvalQueue.previewProcessing')
      pollPreviewStatus()
    } catch (err) {
      log.error('Preview creation failed', err)
      previewLoading.value = false
      notify({
        type: 'negative',
        message: t('pages.approvalQueue.failedToCreatePreview'),
        timeout: 3000,
        position: 'top',
      })
    }
  }

  /** Stop polling, ask the server to discard the job, and reset all state. */
  async function cleanupPreview(): Promise<void> {
    stopPolling()
    if (previewJobId) {
      try {
        await axios.post(getCompressoApiUrl('v2', 'preview/cleanup'), { job_id: previewJobId })
      } catch (err) {
        log.debug('Preview cleanup request failed (ignored)', err)
      }
      previewJobId = null
    }
    resetPreviewState()
  }

  return {
    previewActive,
    previewLoading,
    previewStatus,
    previewData,
    startPreview,
    cleanupPreview,
    resetPreviewState,
  }
}
