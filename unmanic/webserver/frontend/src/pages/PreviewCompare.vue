<template>
  <q-page padding>
    <div class="q-pa-md">
      <div class="text-h5 q-mb-md">A/B Preview Comparison</div>

      <!-- Preview Setup -->
      <q-card class="q-mb-lg" v-if="!previewReady">
        <q-card-section>
          <div class="text-h6">Generate Preview</div>
          <p class="text-caption">Select a file and time range to compare encoding quality side-by-side.</p>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="sourcePath"
            label="Source File Path"
            outlined
            dense
            class="q-mb-md"
            placeholder="/path/to/video.mkv"
          />
          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12 col-sm-4">
              <q-input
                v-model.number="startTime"
                label="Start Time (seconds)"
                type="number"
                outlined
                dense
                :min="0"
              />
            </div>
            <div class="col-12 col-sm-4">
              <q-input
                v-model.number="duration"
                label="Duration (seconds)"
                type="number"
                outlined
                dense
                :min="1"
                :max="30"
              />
            </div>
            <div class="col-12 col-sm-4">
              <q-select
                v-model="libraryId"
                :options="libraryOptions"
                label="Library"
                outlined
                dense
                emit-value
                map-options
              />
            </div>
          </div>
          <q-btn
            color="primary"
            label="Generate Preview"
            :loading="generating"
            :disable="!sourcePath || generating"
            @click="generatePreview"
          />
        </q-card-section>

        <!-- Status -->
        <q-card-section v-if="jobId && !previewReady">
          <q-linear-progress
            v-if="jobStatus === 'running'"
            indeterminate
            color="primary"
            class="q-mb-sm"
          />
          <div v-if="jobStatus === 'running'" class="text-caption">
            Generating preview... This may take a moment.
            <q-btn
              flat
              dense
              color="negative"
              label="Cancel"
              class="q-ml-md"
              @click="cancelPreview"
            />
          </div>
          <div v-if="jobStatus === 'failed'" class="text-negative">
            Preview generation failed: {{ jobError }}
          </div>
        </q-card-section>
      </q-card>

      <!-- Video Comparison -->
      <div v-if="previewReady">
        <q-btn
          flat
          icon="arrow_back"
          label="New Preview"
          class="q-mb-md"
          @click="resetPreview"
        />

        <VideoCompare
          :source-url="sourceUrl"
          :encoded-url="encodedUrl"
          :source-size="sourceSize"
          :encoded-size="encodedSize"
          :source-codec="sourceCodec"
          :encoded-codec="encodedCodec"
          :vmaf-score="vmafScore"
          :ssim-score="ssimScore"
          :encoded-by-pipeline="encodedByPipeline"
        />
      </div>
    </div>
  </q-page>
</template>

<script>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useQuasar } from 'quasar';
import axios from 'axios';
import { getUnmanicApiUrl } from 'src/js/unmanicGlobals';
import VideoCompare from 'components/preview/VideoCompare.vue';

export default {
  name: 'PreviewCompare',
  components: { VideoCompare },
  setup() {
    const $q = useQuasar();
    const sourcePath = ref('');
    const startTime = ref(0);
    const duration = ref(10);
    const libraryId = ref(1);
    const libraryOptions = ref([{ label: 'Default Library', value: 1 }]);
    const generating = ref(false);
    const jobId = ref(null);
    const jobStatus = ref('');
    const jobError = ref('');
    const previewReady = ref(false);
    const sourceUrl = ref('');
    const encodedUrl = ref('');
    const sourceSize = ref(0);
    const encodedSize = ref(0);
    const sourceCodec = ref('');
    const encodedCodec = ref('');
    const vmafScore = ref(null);
    const ssimScore = ref(null);
    const encodedByPipeline = ref(false);
    let pollTimer = null;

    // Load available libraries
    async function loadLibraries() {
      try {
        const response = await axios.get(getUnmanicApiUrl('v2', 'settings/read'));
        if (response.data && response.data.settings) {
          const libs = response.data.settings.libraries || [];
          if (libs.length > 0) {
            libraryOptions.value = libs.map(lib => ({
              label: lib.name || `Library ${lib.id}`,
              value: lib.id,
            }));
            libraryId.value = libs[0].id;
          }
        }
      } catch (error) {
        console.error('Error loading libraries:', error);
        $q.notify({ type: 'negative', message: 'Failed to load libraries' });
      }
    }

    async function generatePreview() {
      generating.value = true;
      jobStatus.value = '';
      jobError.value = '';
      previewReady.value = false;

      try {
        const response = await axios.post(getUnmanicApiUrl('v2', 'preview/create'), {
          source_path: sourcePath.value,
          start_time: startTime.value,
          duration: duration.value,
          library_id: libraryId.value,
        });

        if (response.data && response.data.job_id) {
          jobId.value = response.data.job_id;
          jobStatus.value = 'running';
          startPolling();
        } else {
          jobStatus.value = 'failed';
          jobError.value = 'No job ID returned';
        }
      } catch (error) {
        jobStatus.value = 'failed';
        jobError.value = error.response?.data?.error || error.message;
        $q.notify({ type: 'negative', message: 'Failed to generate preview: ' + (error.response?.data?.error || error.message) });
      } finally {
        generating.value = false;
      }
    }

    function startPolling() {
      stopPolling();
      pollTimer = setInterval(async () => {
        try {
          const response = await axios.post(getUnmanicApiUrl('v2', 'preview/status'), {
            job_id: jobId.value,
          });

          if (response.data) {
            jobStatus.value = response.data.status;
            jobError.value = response.data.error || '';

            if (response.data.status === 'ready') {
              sourceUrl.value = response.data.source_url;
              encodedUrl.value = response.data.encoded_url;
              sourceSize.value = response.data.source_size || 0;
              encodedSize.value = response.data.encoded_size || 0;
              sourceCodec.value = response.data.source_codec || '';
              encodedCodec.value = response.data.encoded_codec || '';
              vmafScore.value = response.data.vmaf_score != null ? response.data.vmaf_score : null;
              ssimScore.value = response.data.ssim_score != null ? response.data.ssim_score : null;
              encodedByPipeline.value = response.data.encoded_by_pipeline || false;
              previewReady.value = true;
              stopPolling();
            } else if (response.data.status === 'failed') {
              stopPolling();
            }
          }
        } catch (error) {
          console.error('Error polling preview status:', error);
          $q.notify({ type: 'negative', message: 'Failed to check preview status' });
        }
      }, 2000);
    }

    function stopPolling() {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    async function cancelPreview() {
      stopPolling();
      if (jobId.value) {
        try {
          await axios.post(getUnmanicApiUrl('v2', 'preview/cleanup'), {
            job_id: jobId.value,
          });
        } catch (error) {
          console.error('Error cleaning up preview:', error);
        }
      }
      jobId.value = null;
      jobStatus.value = '';
      jobError.value = '';
      generating.value = false;
      $q.notify({ type: 'info', message: 'Preview generation cancelled' });
    }

    async function resetPreview() {
      // Clean up the current preview
      if (jobId.value) {
        try {
          await axios.post(getUnmanicApiUrl('v2', 'preview/cleanup'), {
            job_id: jobId.value,
          });
        } catch (error) {
          console.error('Error cleaning up preview:', error);
          $q.notify({ type: 'negative', message: 'Failed to clean up preview' });
        }
      }

      jobId.value = null;
      jobStatus.value = '';
      jobError.value = '';
      previewReady.value = false;
      sourceUrl.value = '';
      encodedUrl.value = '';
      sourceSize.value = 0;
      encodedSize.value = 0;
    }

    onMounted(() => {
      loadLibraries();
    });

    onBeforeUnmount(() => {
      stopPolling();
    });

    return {
      sourcePath,
      startTime,
      duration,
      libraryId,
      libraryOptions,
      generating,
      jobId,
      jobStatus,
      jobError,
      previewReady,
      sourceUrl,
      encodedUrl,
      sourceSize,
      encodedSize,
      sourceCodec,
      encodedCodec,
      vmafScore,
      ssimScore,
      encodedByPipeline,
      generatePreview,
      cancelPreview,
      resetPreview,
    };
  }
}
</script>
