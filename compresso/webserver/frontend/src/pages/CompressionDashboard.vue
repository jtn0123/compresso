<template>
  <q-page padding>
    <div class="q-pa-md">
      <PageHeader :title="$t('pages.compressionDashboard.title')">
        <template #actions>
          <q-select
            v-model="selectedLibraryId"
            :options="libraryOptions"
            :label="$t('pages.compressionDashboard.libraryFilter')"
            outlined
            dense
            emit-value
            map-options
            style="min-width: 200px"
            @update:model-value="onLibraryChange"
          />
        </template>
      </PageHeader>

      <!-- Summary Cards -->
      <div class="row q-col-gutter-md q-mb-lg">
        <div class="col-12 col-sm-6 col-md-3">
          <q-card flat bordered class="stat-card stat-card--primary">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.compressionDashboard.totalSpaceSaved') }}<q-tooltip>{{ $t('pages.compressionDashboard.tooltipSpaceSaved') }}</q-tooltip></div>
              <div class="stat-value">
                <q-skeleton v-if="loadingSummary" type="text" width="60px" />
                <template v-else>{{ formatBytes(summary.space_saved) }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card flat bordered class="stat-card stat-card--secondary">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.compressionDashboard.filesProcessed') }}</div>
              <div class="stat-value">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.file_count }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card flat bordered class="stat-card stat-card--accent">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.compressionDashboard.avgCompressionRatio') }}<q-tooltip>{{ $t('pages.compressionDashboard.tooltipRatio') }}</q-tooltip></div>
              <div class="stat-value">
                <q-skeleton v-if="loadingSummary" type="text" width="50px" />
                <template v-else>{{ (summary.avg_ratio * 100).toFixed(1) }}%</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card flat bordered class="stat-card stat-card--info">
            <q-card-section>
              <div class="stat-label">{{ $t('pages.compressionDashboard.pendingEstimate') }}<q-tooltip>{{ $t('pages.compressionDashboard.tooltipPendingEstimate') }}</q-tooltip></div>
              <div class="stat-value">
                <q-skeleton v-if="loadingSummary" type="text" width="60px" />
                <template v-else>{{ formatBytes(pendingEstimate.estimated_savings) }}</template>
              </div>
              <div class="stat-sublabel">
                <template v-if="!loadingSummary">{{ $t('pages.compressionDashboard.filesCount', { count: pendingEstimate.pending_count }) }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Charts Section -->
      <div class="text-overline text-grey-6 q-mb-sm q-mt-sm">{{ $t('pages.compressionDashboard.sectionDistribution') }}</div>
      <div class="row q-col-gutter-md q-mb-lg">
        <div class="col-12 col-md-6">
          <CodecDistributionChart
            v-if="codecData.source_codecs.length > 0 || codecData.destination_codecs.length > 0 || chartsLoading"
            :source-codecs="codecData.source_codecs"
            :destination-codecs="codecData.destination_codecs"
            :loading="chartsLoading"
          />
          <q-card v-else>
            <q-card-section class="text-center text-grey">{{ $t('pages.compressionDashboard.noCodecData') }}</q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-md-6">
          <ResolutionDistributionChart
            v-if="resolutionData.length > 0 || chartsLoading"
            :resolutions="resolutionData"
            :loading="chartsLoading"
          />
          <q-card v-else>
            <q-card-section class="text-center text-grey">{{ $t('pages.compressionDashboard.noResolutionData') }}</q-card-section>
          </q-card>
        </div>
      </div>

      <div class="text-overline text-grey-6 q-mb-sm">{{ $t('pages.compressionDashboard.sectionTimeline') }}</div>
      <div class="row q-col-gutter-md q-mb-lg">
        <div class="col-12 col-md-6">
          <SpaceSavedTimelineChart
          v-if="timelineData.length > 0 || chartsLoading"
          :data="timelineData"
          :loading="chartsLoading"
          @interval-change="onIntervalChange"
        />
        <q-card v-else>
          <q-card-section class="text-center text-grey">{{ $t('pages.compressionDashboard.noTimelineData') }}</q-card-section>
        </q-card>
        </div>
        <div class="col-12 col-md-6">
          <EncodingSpeedChart
            :data="encodingSpeedData"
            :loading="chartsLoading"
          />
        </div>
      </div>

      <!-- Library Analysis Section -->
      <div class="text-overline text-grey-6 q-mb-sm">{{ $t('pages.compressionDashboard.sectionAnalysis') }}</div>
      <q-card class="q-mb-lg">
        <q-card-section>
          <div class="row items-center no-wrap">
            <div class="col">
              <div class="text-h6">{{ $t('flow.libraryAnalysis') }}</div>
            </div>
            <div class="col-auto q-gutter-sm">
              <q-btn
                v-if="analysisStatus !== 'running'"
                outline
                color="primary"
                :label="analysisResults ? $t('flow.reanalyze') : $t('flow.analyzeButton')"
                icon="analytics"
                :disable="!selectedLibraryId"
                @click="startAnalysis"
              />
            </div>
          </div>
          <div v-if="!selectedLibraryId" class="text-caption text-grey q-mt-sm">
            Select a library to analyze
          </div>
        </q-card-section>

        <!-- Progress bar during analysis -->
        <q-card-section v-if="analysisStatus === 'running'">
          <div class="text-caption q-mb-xs">
            {{ $t('flow.analysisProgress', { checked: analysisProgress.checked || 0, total: analysisProgress.total || 0 }) }}
          </div>
          <q-linear-progress
            :value="analysisProgress.total > 0 ? analysisProgress.checked / analysisProgress.total : 0"
            color="primary"
            rounded
            size="8px"
          />
        </q-card-section>

        <!-- Analysis results -->
        <template v-if="analysisResults && analysisResults.groups">
          <q-card-section>
            <div class="text-body2 q-mb-md">
              {{ analysisResults.total_files }} files ({{ formatBytes(analysisResults.total_size_bytes) }})
              <template v-if="analysisResults.total_estimated_savings_bytes > 0">
                — estimated savings: {{ formatBytes(analysisResults.total_estimated_savings_bytes) }}
              </template>
            </div>

            <q-table
              :rows="analysisResults.groups"
              :columns="analysisColumns"
              row-key="codec"
              flat
              dense
              hide-pagination
              :pagination="{ rowsPerPage: 0 }"
            >
              <template v-slot:body-cell-confidence="cellProps">
                <q-td :cellProps="cellProps">
                  <q-badge
                    :color="confidenceColor(cellProps.row.confidence)"
                    :text-color="cellProps.row.confidence === 'optimal' ? 'dark' : 'white'"
                  >
                    {{ confidenceLabel(cellProps.row.confidence) }}
                    <template v-if="cellProps.row.historical_sample_count > 0">
                      ({{ cellProps.row.historical_sample_count }})
                    </template>
                  </q-badge>
                </q-td>
              </template>
              <template v-slot:body-cell-estimated_savings="cellProps">
                <q-td :cellProps="cellProps">
                  <template v-if="cellProps.row.confidence === 'optimal'">
                    <span class="text-grey">{{ $t('flow.alreadyOptimal') }}</span>
                  </template>
                  <template v-else-if="cellProps.row.confidence === 'none'">
                    <span class="text-grey">{{ $t('flow.noEstimate') }}</span>
                  </template>
                  <template v-else>
                    {{ cellProps.row.estimated_savings_pct }}% (~{{ formatBytes(cellProps.row.estimated_savings_bytes) }})
                  </template>
                </q-td>
              </template>
            </q-table>
          </q-card-section>
          <q-card-section v-if="analysisResults.last_run" class="text-caption text-grey">
            {{ $t('flow.lastAnalyzed') }}: {{ analysisResults.last_run }}
            — {{ $t('flow.estimatesLive') }}
          </q-card-section>
        </template>
      </q-card>

      <!-- Per-Library Breakdown -->
      <q-card class="q-mb-lg" v-if="summary.per_library && summary.per_library.length > 0">
        <q-card-section>
          <div class="text-h6">{{ $t('pages.compressionDashboard.perLibraryBreakdown') }}</div>
        </q-card-section>
        <q-table
          :rows="summary.per_library"
          :columns="libraryColumns"
          row-key="library_id"
          flat
          dense
          hide-pagination
          :pagination="{ rowsPerPage: 0 }"
        />
      </q-card>

      <!-- Per-File Table -->
      <q-card>
        <q-card-section>
          <div class="text-h6">{{ $t('pages.compressionDashboard.perFileStats') }}</div>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="searchValue"
            debounce="500"
            :placeholder="$t('pages.compressionDashboard.searchFiles')"
            dense
            outlined
            class="q-mb-md"
            @update:model-value="loadStats"
          >
            <template v-slot:prepend>
              <q-icon name="search" />
            </template>
          </q-input>

          <q-table
            :rows="statsResults"
            :columns="fileColumns"
            row-key="id"
            flat
            dense
            :loading="loading"
            :pagination="pagination"
            @request="onTableRequest"
          >
            <template v-slot:body-cell-ratio="props">
              <q-td :props="props">
                <q-badge
                  :color="props.row.ratio < 1 ? 'positive' : 'negative'"
                >
                  {{ (props.row.ratio * 100).toFixed(1) }}%
                </q-badge>
              </q-td>
            </template>
            <template v-slot:body-cell-space_saved="props">
              <q-td :props="props">
                <span :class="props.row.space_saved > 0 ? 'text-positive' : 'text-negative'">
                  {{ formatBytes(props.row.space_saved) }}
                </span>
              </q-td>
            </template>
          </q-table>
        </q-card-section>
      </q-card>
    </div>
  </q-page>
</template>

<script>
import { ref, onMounted } from 'vue';
import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';
import axios from 'axios';
import { getCompressoApiUrl } from 'src/js/compressoGlobals';
import { formatBytes } from 'src/js/formatUtils';
import CodecDistributionChart from 'components/charts/CodecDistributionChart.vue';
import ResolutionDistributionChart from 'components/charts/ResolutionDistributionChart.vue';
import SpaceSavedTimelineChart from 'components/charts/SpaceSavedTimelineChart.vue';
import EncodingSpeedChart from 'components/charts/EncodingSpeedChart.vue';
import PageHeader from 'components/ui/PageHeader.vue';

export default {
  name: 'CompressionDashboard',
  components: {
    CodecDistributionChart,
    ResolutionDistributionChart,
    SpaceSavedTimelineChart,
    EncodingSpeedChart,
    PageHeader,
  },
  setup() {
    const $q = useQuasar();
    const { t } = useI18n();
    const loadingSummary = ref(true);
    const selectedLibraryId = ref(null);
    const libraryOptions = ref([{ label: t('pages.compressionDashboard.allLibraries'), value: null }]);

    const summary = ref({
      total_source_size: 0,
      total_destination_size: 0,
      file_count: 0,
      avg_ratio: 0,
      space_saved: 0,
      per_library: [],
    });

    const pendingEstimate = ref({
      pending_count: 0,
      total_pending_size: 0,
      estimated_output_size: 0,
      estimated_savings: 0,
      avg_ratio_used: 1.0,
    });

    const codecData = ref({ source_codecs: [], destination_codecs: [] });
    const resolutionData = ref([]);
    const timelineData = ref([]);
    const timelineInterval = ref('day');
    const chartsLoading = ref(false);
    const encodingSpeedData = ref([]);

    const analysisStatus = ref('none');
    const analysisProgress = ref({ checked: 0, total: 0 });
    const analysisResults = ref(null);
    const analysisVersion = ref(0);
    let analysisPollTimer = null;

    const analysisColumns = [
      { name: 'codec', label: t('flow.analysisCodec'), field: 'codec', align: 'left' },
      { name: 'resolution', label: t('flow.analysisResolution'), field: 'resolution', align: 'left' },
      { name: 'count', label: t('flow.analysisCount'), field: 'count', align: 'right', sortable: true },
      { name: 'total_size_bytes', label: t('flow.analysisTotalSize'), field: 'total_size_bytes', align: 'right', format: (v) => formatBytes(v) },
      { name: 'avg_bitrate_mbps', label: t('flow.analysisAvgBitrate'), field: 'avg_bitrate_mbps', align: 'right', format: (v) => v > 0 ? v.toFixed(1) + ' Mbps' : '-' },
      { name: 'estimated_savings', label: t('flow.analysisEstSavings'), field: 'estimated_savings_pct', align: 'right' },
      { name: 'confidence', label: t('flow.analysisConfidence'), field: 'confidence', align: 'center' },
    ];

    function confidenceColor(level) {
      const map = { high: 'positive', medium: 'warning', low: 'grey', none: 'grey-4', optimal: 'grey-4' };
      return map[level] || 'grey';
    }
    function confidenceLabel(level) {
      const map = {
        high: t('flow.confidenceHigh'),
        medium: t('flow.confidenceMedium'),
        low: t('flow.confidenceLow'),
        none: t('flow.confidenceNone'),
        optimal: t('flow.alreadyOptimal'),
      };
      return map[level] || level;
    }

    async function startAnalysis() {
      if (!selectedLibraryId.value) return;
      try {
        await axios.post(getCompressoApiUrl('v2', 'compression/library-analysis'), {
          library_id: selectedLibraryId.value,
        });
        analysisStatus.value = 'running';
        pollAnalysisStatus();
      } catch (error) {
        console.error('Error starting analysis:', error);
      }
    }

    async function pollAnalysisStatus() {
      if (!selectedLibraryId.value) return;
      try {
        const response = await axios.post(getCompressoApiUrl('v2', 'compression/library-analysis/status'), {
          library_id: selectedLibraryId.value,
        });
        if (response.data) {
          analysisStatus.value = response.data.status || 'none';
          analysisProgress.value = response.data.progress || { checked: 0, total: 0 };
          if (response.data.results) {
            analysisResults.value = response.data.results;
            analysisVersion.value = response.data.version || 0;
          }
        }
        if (analysisStatus.value === 'running') {
          analysisPollTimer = setTimeout(pollAnalysisStatus, 2000);
        }
      } catch (error) {
        console.error('Error polling analysis status:', error);
        analysisStatus.value = 'error';
      }
    }

    async function loadAnalysisIfAvailable() {
      if (!selectedLibraryId.value) return;
      try {
        const response = await axios.post(getCompressoApiUrl('v2', 'compression/library-analysis/status'), {
          library_id: selectedLibraryId.value,
        });
        if (response.data) {
          analysisStatus.value = response.data.status || 'none';
          analysisProgress.value = response.data.progress || { checked: 0, total: 0 };
          if (response.data.results) {
            analysisResults.value = response.data.results;
            analysisVersion.value = response.data.version || 0;
          }
          if (analysisStatus.value === 'running') {
            analysisPollTimer = setTimeout(pollAnalysisStatus, 2000);
          }
        }
      } catch (error) {
        // No analysis available — that's fine
      }
    }

    const statsResults = ref([]);
    const searchValue = ref('');
    const loading = ref(false);
    const pagination = ref({
      page: 1,
      rowsPerPage: 20,
      rowsNumber: 0,
      sortBy: 'finish_time',
      descending: true,
    });

    const libraryColumns = [
      { name: 'library_id', label: t('pages.compressionDashboard.columnLibraryId'), field: 'library_id', align: 'left', sortable: true },
      { name: 'file_count', label: t('pages.compressionDashboard.columnFiles'), field: 'file_count', align: 'right', sortable: true },
      { name: 'total_source_size', label: t('pages.compressionDashboard.columnOriginalSize'), field: 'total_source_size', align: 'right', format: (v) => formatBytes(v) },
      { name: 'total_destination_size', label: t('pages.compressionDashboard.columnNewSize'), field: 'total_destination_size', align: 'right', format: (v) => formatBytes(v) },
      { name: 'space_saved', label: t('pages.compressionDashboard.columnSpaceSaved'), field: 'space_saved', align: 'right', format: (v) => formatBytes(v) },
      { name: 'avg_ratio', label: t('pages.compressionDashboard.columnAvgRatio'), field: 'avg_ratio', align: 'right', format: (v) => (v * 100).toFixed(1) + '%' },
    ];

    const fileColumns = [
      { name: 'task_label', label: t('pages.compressionDashboard.columnFile'), field: 'task_label', align: 'left', sortable: true },
      { name: 'source_size', label: t('pages.compressionDashboard.columnOriginal'), field: 'source_size', align: 'right', sortable: true, format: (v) => formatBytes(v) },
      { name: 'destination_size', label: t('pages.compressionDashboard.columnNewSize'), field: 'destination_size', align: 'right', sortable: true, format: (v) => formatBytes(v) },
      { name: 'ratio', label: t('pages.compressionDashboard.columnRatio'), field: 'ratio', align: 'center', sortable: true },
      { name: 'space_saved', label: t('pages.compressionDashboard.columnSaved'), field: 'space_saved', align: 'right', sortable: true },
      { name: 'source_codec', label: t('pages.compressionDashboard.columnSourceCodec'), field: 'source_codec', align: 'left' },
      { name: 'destination_codec', label: t('pages.compressionDashboard.columnDestCodec'), field: 'destination_codec', align: 'left' },
      { name: 'library_id', label: t('pages.compressionDashboard.columnLibrary'), field: 'library_id', align: 'center' },
      { name: 'finish_time', label: t('pages.compressionDashboard.columnDate'), field: 'finish_time', align: 'left', sortable: true },
    ];

    function buildLibraryParam() {
      return selectedLibraryId.value !== null ? '?library_id=' + selectedLibraryId.value : '';
    }

    async function loadSummary() {
      try {
        const response = await axios.get(getCompressoApiUrl('v2', 'compression/summary') + buildLibraryParam());
        if (response.data) {
          summary.value = response.data;
        }
      } catch (error) {
        console.error('Error loading compression summary:', error);
        $q.notify({ type: 'negative', message: t('pages.compressionDashboard.errorLoadingSummary') });
      } finally {
        loadingSummary.value = false;
      }
    }

    async function loadPendingEstimate() {
      try {
        const response = await axios.get(getCompressoApiUrl('v2', 'compression/pending-estimate'));
        if (response.data) {
          pendingEstimate.value = response.data;
        }
      } catch (error) {
        console.error('Error loading pending estimate:', error);
        $q.notify({ type: 'negative', message: t('pages.compressionDashboard.errorLoadingPendingEstimate') });
      }
    }

    async function loadCharts() {
      chartsLoading.value = true;
      try {
        const param = buildLibraryParam();
        const results = await Promise.allSettled([
          axios.get(getCompressoApiUrl('v2', 'compression/codec-distribution') + param),
          axios.get(getCompressoApiUrl('v2', 'compression/resolution-distribution') + param),
          axios.get(getCompressoApiUrl('v2', 'compression/timeline') + param + (param ? '&' : '?') + 'interval=' + timelineInterval.value),
          axios.get(getCompressoApiUrl('v2', 'compression/encoding-speed') + param),
        ]);
        if (results[0].status === 'fulfilled' && results[0].value.data) codecData.value = results[0].value.data;
        if (results[1].status === 'fulfilled' && results[1].value.data) resolutionData.value = results[1].value.data.resolutions || [];
        if (results[2].status === 'fulfilled' && results[2].value.data) timelineData.value = results[2].value.data.data || [];
        if (results[3].status === 'fulfilled' && results[3].value.data) encodingSpeedData.value = results[3].value.data.data || [];
      } catch (error) {
        console.error('Error loading chart data:', error);
      } finally {
        chartsLoading.value = false;
      }
    }

    async function loadStats() {
      loading.value = true;
      try {
        const start = (pagination.value.page - 1) * pagination.value.rowsPerPage;
        const response = await axios.post(getCompressoApiUrl('v2', 'compression/stats'), {
          start: start,
          length: pagination.value.rowsPerPage,
          search_value: searchValue.value,
          library_id: selectedLibraryId.value,
          order_by: pagination.value.sortBy || 'finish_time',
          order_direction: pagination.value.descending ? 'desc' : 'asc',
        });
        if (response.data) {
          statsResults.value = response.data.results || [];
          pagination.value.rowsNumber = response.data.recordsFiltered || 0;
        }
      } catch (error) {
        console.error('Error loading compression stats:', error);
        $q.notify({ type: 'negative', message: t('pages.compressionDashboard.errorLoadingStats') });
      } finally {
        loading.value = false;
      }
    }

    function onTableRequest(props) {
      const { page, rowsPerPage, sortBy, descending } = props.pagination;
      pagination.value.page = page;
      pagination.value.rowsPerPage = rowsPerPage;
      pagination.value.sortBy = sortBy;
      pagination.value.descending = descending;
      loadStats();
    }

    async function onLibraryChange() {
      pagination.value.page = 1;
      analysisResults.value = null;
      analysisStatus.value = 'none';
      if (analysisPollTimer) clearTimeout(analysisPollTimer);
      await Promise.all([loadSummary(), loadCharts(), loadStats(), loadAnalysisIfAvailable()]);
    }

    function onIntervalChange(newInterval) {
      timelineInterval.value = newInterval;
      loadCharts();
    }

    async function loadLibraries() {
      try {
        const response = await axios.get(getCompressoApiUrl('v2', 'settings/read'));
        if (response.data && response.data.settings) {
          const libs = response.data.settings.libraries || [];
          libraryOptions.value = [{ label: t('pages.compressionDashboard.allLibraries'), value: null }];
          libs.forEach(lib => {
            libraryOptions.value.push({
              label: lib.name || `Library ${lib.id}`,
              value: lib.id,
            });
          });
        }
      } catch (error) {
        console.error('Error loading libraries:', error);
        $q.notify({ type: 'negative', message: t('pages.compressionDashboard.errorLoadingLibraries') });
      }
    }

    onMounted(async () => {
      await loadLibraries();
      await Promise.all([loadSummary(), loadPendingEstimate(), loadCharts(), loadStats()]);
    });

    return {
      selectedLibraryId,
      libraryOptions,
      loadingSummary,
      summary,
      pendingEstimate,
      codecData,
      resolutionData,
      timelineData,
      encodingSpeedData,
      chartsLoading,
      statsResults,
      searchValue,
      loading,
      pagination,
      libraryColumns,
      fileColumns,
      analysisColumns,
      analysisStatus,
      analysisProgress,
      analysisResults,
      analysisVersion,
      formatBytes,
      loadStats,
      onTableRequest,
      onLibraryChange,
      onIntervalChange,
      startAnalysis,
      confidenceColor,
      confidenceLabel,
    };
  }
}
</script>
