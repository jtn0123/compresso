import { ref } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { createLogger } from 'src/composables/useLogger'

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
export function usePreviewJob({ notify, t }) {
  const previewActive = ref(false)
  const previewLoading = ref(false)
  const previewStatus = ref('')
  const previewData = ref(null)
  let previewJobId = null
  let previewPollInterval = null

  function resetPreviewState() {
    previewActive.value = false
    previewLoading.value = false
    previewData.value = null
  }

  function pollPreviewStatus() {
    previewPollInterval = setInterval(async () => {
      try {
        const res = await axios.post(getCompressoApiUrl('v2', 'preview/status'), { job_id: previewJobId })
        const status = res.data.status
        previewStatus.value = status
        if (status === 'complete') {
          clearInterval(previewPollInterval)
          previewPollInterval = null
          previewData.value = res.data
          previewLoading.value = false
          previewActive.value = true
        } else if (status === 'error' || status === 'failed') {
          clearInterval(previewPollInterval)
          previewPollInterval = null
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
        clearInterval(previewPollInterval)
        previewPollInterval = null
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
  async function startPreview({ sourcePath, libraryId = 1, startTime = 0, duration = 10 }) {
    previewLoading.value = true
    previewStatus.value = t('pages.approvalQueue.previewStarting')
    try {
      const res = await axios.post(getCompressoApiUrl('v2', 'preview/create'), {
        source_path: sourcePath,
        start_time: startTime,
        duration: duration,
        library_id: libraryId,
      })
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
  async function cleanupPreview() {
    if (previewPollInterval) {
      clearInterval(previewPollInterval)
      previewPollInterval = null
    }
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
