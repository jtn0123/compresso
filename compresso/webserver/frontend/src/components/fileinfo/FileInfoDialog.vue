<template>
  <q-dialog v-model="dialogVisible" persistent maximized transition-show="slide-up" transition-hide="slide-down">
    <q-card>
      <q-bar class="bg-primary text-white">
        <div class="text-subtitle1">File Info</div>
        <q-space />
        <q-btn dense flat icon="close" @click="hide" />
      </q-bar>

      <q-card-section v-if="loading" class="text-center q-pa-xl">
        <q-spinner-gears size="50px" color="primary" />
        <div class="q-mt-md text-caption">Probing file...</div>
      </q-card-section>

      <q-card-section v-if="error" class="text-center q-pa-xl">
        <q-icon name="error" color="negative" size="50px" />
        <div class="q-mt-md text-negative">{{ error }}</div>
      </q-card-section>

      <q-card-section v-if="!loading && !error && fileInfo" class="q-pa-md">
        <!-- Format Info -->
        <q-expansion-item default-opened icon="info" label="Format" caption="Container and general file info">
          <q-card>
            <q-card-section>
              <div class="row q-col-gutter-sm">
                <div class="col-6 col-sm-4"><strong>Format:</strong> {{ fileInfo.format.format_name }}</div>
                <div class="col-6 col-sm-4"><strong>Duration:</strong> {{ formatDuration(fileInfo.format.duration) }}</div>
                <div class="col-6 col-sm-4"><strong>Size:</strong> {{ formatBytes(fileInfo.format.size) }}</div>
                <div class="col-6 col-sm-4"><strong>Bitrate:</strong> {{ formatBitrate(fileInfo.format.bit_rate) }}</div>
                <div class="col-6 col-sm-4"><strong>Streams:</strong> {{ fileInfo.format.nb_streams }}</div>
              </div>
            </q-card-section>
          </q-card>
        </q-expansion-item>

        <!-- Video Streams -->
        <q-expansion-item
          v-if="fileInfo.video_streams && fileInfo.video_streams.length > 0"
          default-opened
          icon="videocam"
          :label="`Video Streams (${fileInfo.video_streams.length})`"
        >
          <q-card v-for="(stream, idx) in fileInfo.video_streams" :key="'v' + idx" class="q-mb-sm">
            <q-card-section>
              <div class="row items-center q-mb-sm">
                <span class="text-subtitle2">Stream #{{ stream.index }}</span>
                <q-badge class="q-ml-sm" color="primary">{{ stream.codec_name }}</q-badge>
                <q-badge v-if="stream.resolution_label" class="q-ml-sm" color="secondary">{{ stream.resolution_label }}</q-badge>
                <q-badge v-if="stream.hdr" class="q-ml-sm" color="amber" text-color="black">HDR</q-badge>
              </div>
              <div class="row q-col-gutter-sm">
                <div class="col-6 col-sm-3"><strong>Resolution:</strong> {{ stream.width }}x{{ stream.height }}</div>
                <div class="col-6 col-sm-3"><strong>Codec:</strong> {{ stream.codec_long_name }}</div>
                <div class="col-6 col-sm-3"><strong>Profile:</strong> {{ stream.profile || 'N/A' }}</div>
                <div class="col-6 col-sm-3"><strong>Bitrate:</strong> {{ formatBitrate(stream.bit_rate) }}</div>
                <div class="col-6 col-sm-3"><strong>Frame Rate:</strong> {{ stream.r_frame_rate }}</div>
                <div class="col-6 col-sm-3"><strong>Pixel Format:</strong> {{ stream.pix_fmt }}</div>
                <div v-if="stream.color_space" class="col-6 col-sm-3"><strong>Color Space:</strong> {{ stream.color_space }}</div>
                <div v-if="stream.color_transfer" class="col-6 col-sm-3"><strong>Color Transfer:</strong> {{ stream.color_transfer }}</div>
              </div>
            </q-card-section>
          </q-card>
        </q-expansion-item>

        <!-- Audio Streams -->
        <q-expansion-item
          v-if="fileInfo.audio_streams && fileInfo.audio_streams.length > 0"
          default-opened
          icon="audiotrack"
          :label="`Audio Streams (${fileInfo.audio_streams.length})`"
        >
          <q-card v-for="(stream, idx) in fileInfo.audio_streams" :key="'a' + idx" class="q-mb-sm">
            <q-card-section>
              <div class="row items-center q-mb-sm">
                <span class="text-subtitle2">Stream #{{ stream.index }}</span>
                <q-badge class="q-ml-sm" color="primary">{{ stream.codec_name }}</q-badge>
                <q-badge v-if="stream.language" class="q-ml-sm" color="grey">{{ stream.language }}</q-badge>
              </div>
              <div class="row q-col-gutter-sm">
                <div class="col-6 col-sm-3"><strong>Codec:</strong> {{ stream.codec_long_name }}</div>
                <div class="col-6 col-sm-3"><strong>Channels:</strong> {{ stream.channels }} ({{ stream.channel_layout || 'N/A' }})</div>
                <div class="col-6 col-sm-3"><strong>Sample Rate:</strong> {{ stream.sample_rate ? stream.sample_rate + ' Hz' : 'N/A' }}</div>
                <div class="col-6 col-sm-3"><strong>Bitrate:</strong> {{ formatBitrate(stream.bit_rate) }}</div>
                <div v-if="stream.title" class="col-6 col-sm-3"><strong>Title:</strong> {{ stream.title }}</div>
              </div>
            </q-card-section>
          </q-card>
        </q-expansion-item>

        <!-- Subtitle Streams -->
        <q-expansion-item
          v-if="fileInfo.subtitle_streams && fileInfo.subtitle_streams.length > 0"
          icon="subtitles"
          :label="`Subtitle Streams (${fileInfo.subtitle_streams.length})`"
        >
          <q-card v-for="(stream, idx) in fileInfo.subtitle_streams" :key="'s' + idx" class="q-mb-sm">
            <q-card-section>
              <div class="row items-center">
                <span class="text-subtitle2">Stream #{{ stream.index }}</span>
                <q-badge class="q-ml-sm" color="primary">{{ stream.codec_name }}</q-badge>
                <q-badge v-if="stream.language" class="q-ml-sm" color="grey">{{ stream.language }}</q-badge>
                <span v-if="stream.title" class="q-ml-sm text-caption">{{ stream.title }}</span>
              </div>
            </q-card-section>
          </q-card>
        </q-expansion-item>

        <!-- Health Badge (if available) -->
        <div v-if="healthStatus" class="q-mt-md">
          <q-badge :color="healthBadgeColor" class="text-body2 q-pa-sm">
            Health: {{ healthStatus }}
          </q-badge>
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script>
import { ref, computed } from 'vue';
import axios from 'axios';
import { getCompressoApiUrl } from 'src/js/compressoGlobals';
import { formatBytes as sharedFormatBytes, formatBitrate as sharedFormatBitrate, formatDuration as sharedFormatDuration } from 'src/js/formatUtils';

export default {
  name: 'FileInfoDialog',
  props: {
    healthStatus: { type: String, default: '' },
  },
  setup(props) {
    const dialogVisible = ref(false);
    const loading = ref(false);
    const error = ref('');
    const fileInfo = ref(null);

    const healthBadgeColor = computed(() => {
      if (props.healthStatus === 'healthy') return 'positive';
      if (props.healthStatus === 'corrupted') return 'negative';
      if (props.healthStatus === 'checking') return 'warning';
      return 'grey';
    });

    function show() {
      dialogVisible.value = true;
    }

    function hide() {
      dialogVisible.value = false;
    }

    async function probeByPath(filePath) {
      loading.value = true;
      error.value = '';
      fileInfo.value = null;
      show();

      try {
        const response = await axios.post(getCompressoApiUrl('v2', 'fileinfo/probe'), {
          file_path: filePath,
        });
        if (response.data && response.data.success) {
          fileInfo.value = response.data;
        } else {
          error.value = 'Failed to probe file';
        }
      } catch (err) {
        error.value = err.response?.data?.error || err.message || 'Failed to probe file';
      } finally {
        loading.value = false;
      }
    }

    async function probeByTaskId(taskId) {
      loading.value = true;
      error.value = '';
      fileInfo.value = null;
      show();

      try {
        const response = await axios.post(getCompressoApiUrl('v2', 'fileinfo/task'), {
          task_id: taskId,
        });
        if (response.data && response.data.success) {
          fileInfo.value = response.data;
        } else {
          error.value = 'Failed to probe task file';
        }
      } catch (err) {
        error.value = err.response?.data?.error || err.message || 'Failed to probe task file';
      } finally {
        loading.value = false;
      }
    }

    function formatBytes(bytes) {
      if (!bytes || bytes === 0) return 'N/A';
      return sharedFormatBytes(bytes);
    }

    function formatBitrate(bps) {
      if (!bps || bps === 0) return 'N/A';
      return sharedFormatBitrate(bps);
    }

    function formatDuration(seconds) {
      if (!seconds || seconds === 0) return 'N/A';
      return sharedFormatDuration(seconds);
    }

    return {
      dialogVisible,
      loading,
      error,
      fileInfo,
      healthBadgeColor,
      show,
      hide,
      probeByPath,
      probeByTaskId,
      formatBytes,
      formatBitrate,
      formatDuration,
    };
  },
};
</script>
