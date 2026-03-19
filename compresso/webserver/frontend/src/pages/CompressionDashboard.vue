<template>
  <q-page padding>
    <div class="q-pa-md">
      <div class="row items-center q-mb-md">
        <div class="text-h5 col">Compression Dashboard</div>
        <q-select
          v-model="selectedLibraryId"
          :options="libraryOptions"
          label="Library Filter"
          outlined
          dense
          emit-value
          map-options
          style="min-width: 200px"
          @update:model-value="onLibraryChange"
        />
      </div>

      <!-- Summary Cards -->
      <div class="row q-col-gutter-md q-mb-lg">
        <div class="col-12 col-sm-6 col-md-3">
          <q-card class="bg-primary text-white">
            <q-card-section>
              <div class="text-caption">Total Space Saved</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="60px" />
                <template v-else>{{ formatBytes(summary.space_saved) }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card class="bg-secondary text-white">
            <q-card-section>
              <div class="text-caption">Files Processed</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="40px" />
                <template v-else>{{ summary.file_count }}</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card class="bg-accent text-white">
            <q-card-section>
              <div class="text-caption">Avg Compression Ratio</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="50px" />
                <template v-else>{{ (summary.avg_ratio * 100).toFixed(1) }}%</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-sm-6 col-md-3">
          <q-card class="bg-info text-white">
            <q-card-section>
              <div class="text-caption">Pending Estimate</div>
              <div class="text-h5">
                <q-skeleton v-if="loadingSummary" type="text" width="60px" />
                <template v-else>{{ formatBytes(pendingEstimate.estimated_savings) }}</template>
              </div>
              <div class="text-caption">
                <template v-if="!loadingSummary">{{ pendingEstimate.pending_count }} files</template>
              </div>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Charts Section -->
      <div class="row q-col-gutter-md q-mb-lg">
        <div class="col-12 col-md-6">
          <CodecDistributionChart
            v-if="codecData.source_codecs.length > 0 || codecData.destination_codecs.length > 0 || chartsLoading"
            :source-codecs="codecData.source_codecs"
            :destination-codecs="codecData.destination_codecs"
            :loading="chartsLoading"
          />
          <q-card v-else>
            <q-card-section class="text-center text-grey">No codec data yet</q-card-section>
          </q-card>
        </div>
        <div class="col-12 col-md-6">
          <ResolutionDistributionChart
            v-if="resolutionData.length > 0 || chartsLoading"
            :resolutions="resolutionData"
            :loading="chartsLoading"
          />
          <q-card v-else>
            <q-card-section class="text-center text-grey">No resolution data yet</q-card-section>
          </q-card>
        </div>
      </div>

      <div class="q-mb-lg">
        <SpaceSavedTimelineChart
          v-if="timelineData.length > 0 || chartsLoading"
          :data="timelineData"
          :loading="chartsLoading"
          @interval-change="onIntervalChange"
        />
        <q-card v-else>
          <q-card-section class="text-center text-grey">No timeline data yet</q-card-section>
        </q-card>
      </div>

      <!-- Per-Library Breakdown -->
      <q-card class="q-mb-lg" v-if="summary.per_library && summary.per_library.length > 0">
        <q-card-section>
          <div class="text-h6">Per-Library Breakdown</div>
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
          <div class="text-h6">Per-File Compression Stats</div>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="searchValue"
            debounce="500"
            placeholder="Search files..."
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
import axios from 'axios';
import { getCompressoApiUrl } from 'src/js/compressoGlobals';
import { formatBytes } from 'src/js/formatUtils';
import CodecDistributionChart from 'components/charts/CodecDistributionChart.vue';
import ResolutionDistributionChart from 'components/charts/ResolutionDistributionChart.vue';
import SpaceSavedTimelineChart from 'components/charts/SpaceSavedTimelineChart.vue';

export default {
  name: 'CompressionDashboard',
  components: {
    CodecDistributionChart,
    ResolutionDistributionChart,
    SpaceSavedTimelineChart,
  },
  setup() {
    const $q = useQuasar();
    const loadingSummary = ref(true);
    const selectedLibraryId = ref(null);
    const libraryOptions = ref([{ label: 'All Libraries', value: null }]);

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
      { name: 'library_id', label: 'Library ID', field: 'library_id', align: 'left', sortable: true },
      { name: 'file_count', label: 'Files', field: 'file_count', align: 'right', sortable: true },
      { name: 'total_source_size', label: 'Original Size', field: 'total_source_size', align: 'right', format: (v) => formatBytes(v) },
      { name: 'total_destination_size', label: 'New Size', field: 'total_destination_size', align: 'right', format: (v) => formatBytes(v) },
      { name: 'space_saved', label: 'Space Saved', field: 'space_saved', align: 'right', format: (v) => formatBytes(v) },
      { name: 'avg_ratio', label: 'Avg Ratio', field: 'avg_ratio', align: 'right', format: (v) => (v * 100).toFixed(1) + '%' },
    ];

    const fileColumns = [
      { name: 'task_label', label: 'File', field: 'task_label', align: 'left', sortable: true },
      { name: 'source_size', label: 'Original', field: 'source_size', align: 'right', sortable: true, format: (v) => formatBytes(v) },
      { name: 'destination_size', label: 'New Size', field: 'destination_size', align: 'right', sortable: true, format: (v) => formatBytes(v) },
      { name: 'ratio', label: 'Ratio', field: 'ratio', align: 'center', sortable: true },
      { name: 'space_saved', label: 'Saved', field: 'space_saved', align: 'right', sortable: true },
      { name: 'source_codec', label: 'Source Codec', field: 'source_codec', align: 'left' },
      { name: 'destination_codec', label: 'Dest Codec', field: 'destination_codec', align: 'left' },
      { name: 'library_id', label: 'Library', field: 'library_id', align: 'center' },
      { name: 'finish_time', label: 'Date', field: 'finish_time', align: 'left', sortable: true },
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
        $q.notify({ type: 'negative', message: 'Failed to load compression summary' });
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
        $q.notify({ type: 'negative', message: 'Failed to load pending estimate' });
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
        ]);
        if (results[0].status === 'fulfilled' && results[0].value.data) codecData.value = results[0].value.data;
        if (results[1].status === 'fulfilled' && results[1].value.data) resolutionData.value = results[1].value.data.resolutions || [];
        if (results[2].status === 'fulfilled' && results[2].value.data) timelineData.value = results[2].value.data.data || [];
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
        $q.notify({ type: 'negative', message: 'Failed to load compression stats' });
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
      await Promise.all([loadSummary(), loadCharts(), loadStats()]);
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
          libraryOptions.value = [{ label: 'All Libraries', value: null }];
          libs.forEach(lib => {
            libraryOptions.value.push({
              label: lib.name || `Library ${lib.id}`,
              value: lib.id,
            });
          });
        }
      } catch (error) {
        console.error('Error loading libraries:', error);
        $q.notify({ type: 'negative', message: 'Failed to load libraries' });
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
      chartsLoading,
      statsResults,
      searchValue,
      loading,
      pagination,
      libraryColumns,
      fileColumns,
      formatBytes,
      loadStats,
      onTableRequest,
      onLibraryChange,
      onIntervalChange,
    };
  }
}
</script>
