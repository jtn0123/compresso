<template>
  <q-page class="q-pa-md">

    <!-- Header -->
    <div class="row items-center q-mb-md">
      <div class="col">
        <div class="text-h5">Approval Queue</div>
        <div class="text-caption text-grey">
          Review transcoded files before replacing originals
        </div>
      </div>
      <div class="col-auto q-gutter-sm">
        <q-btn
          color="positive"
          icon="check_circle"
          label="Approve Selected"
          :disable="selectedIds.length === 0"
          @click="approveSelected"/>
        <q-btn
          color="negative"
          icon="cancel"
          label="Reject Selected"
          :disable="selectedIds.length === 0"
          @click="showRejectDialog = true"/>
        <q-btn
          flat
          icon="refresh"
          @click="fetchTasks"/>
      </div>
    </div>

    <!-- Tasks Table -->
    <q-table
      :rows="tasks"
      :columns="columns"
      row-key="id"
      :loading="loading"
      selection="multiple"
      v-model:selected="selected"
      :pagination="pagination"
      @request="onRequest"
      flat
      bordered
      dense
    >
      <!-- File name column -->
      <template v-slot:body-cell-abspath="props">
        <q-td :props="props">
          <div class="text-weight-medium ellipsis" style="max-width: 400px">
            {{ fileName(props.row.abspath) }}
          </div>
          <div class="text-caption text-grey ellipsis" style="max-width: 400px">
            {{ props.row.abspath }}
          </div>
        </q-td>
      </template>

      <!-- Source size column -->
      <template v-slot:body-cell-source_size="props">
        <q-td :props="props">
          {{ formatSize(props.row.source_size) }}
        </q-td>
      </template>

      <!-- Staged size column -->
      <template v-slot:body-cell-staged_size="props">
        <q-td :props="props">
          {{ formatSize(props.row.staged_size) }}
        </q-td>
      </template>

      <!-- Size delta column -->
      <template v-slot:body-cell-size_delta="props">
        <q-td :props="props">
          <q-badge
            :color="props.row.size_delta < 0 ? 'positive' : props.row.size_delta > 0 ? 'negative' : 'grey'"
            :label="formatSizeDelta(props.row.size_delta)"
          />
        </q-td>
      </template>

      <!-- Savings column -->
      <template v-slot:body-cell-savings="props">
        <q-td :props="props">
          <span v-if="props.row.source_size > 0">
            {{ savingsPercent(props.row) }}%
          </span>
          <span v-else>—</span>
        </q-td>
      </template>

      <!-- Actions column -->
      <template v-slot:body-cell-actions="props">
        <q-td :props="props">
          <q-btn
            flat
            dense
            color="positive"
            icon="check"
            size="sm"
            @click.stop="approveSingle(props.row.id)">
            <q-tooltip>Approve</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            color="negative"
            icon="close"
            size="sm"
            @click.stop="rejectSingle(props.row.id)">
            <q-tooltip>Reject</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            color="info"
            icon="info"
            size="sm"
            @click.stop="showDetail(props.row.id)">
            <q-tooltip>Details</q-tooltip>
          </q-btn>
        </q-td>
      </template>

      <!-- No data -->
      <template v-slot:no-data>
        <div class="full-width column items-center q-pa-lg text-grey">
          <q-icon name="check_circle_outline" size="3rem" class="q-mb-sm"/>
          <div class="text-h6">No tasks awaiting approval</div>
          <div class="text-caption">
            Transcoded files will appear here when approval mode is enabled
          </div>
        </div>
      </template>
    </q-table>

    <!-- Detail Dialog -->
    <q-dialog v-model="showDetailDialog" persistent>
      <q-card style="min-width: 500px; max-width: 700px">
        <q-card-section>
          <div class="text-h6">Task Detail</div>
        </q-card-section>
        <q-card-section v-if="detailData">
          <q-list dense>
            <q-item>
              <q-item-section>
                <q-item-label caption>File</q-item-label>
                <q-item-label class="ellipsis">{{ detailData.abspath }}</q-item-label>
              </q-item-section>
            </q-item>
            <q-separator/>
            <q-item>
              <q-item-section>
                <q-item-label caption>Original Size</q-item-label>
                <q-item-label>{{ formatSize(detailData.source_size) }}</q-item-label>
              </q-item-section>
              <q-item-section>
                <q-item-label caption>Transcoded Size</q-item-label>
                <q-item-label>{{ formatSize(detailData.staged_size) }}</q-item-label>
              </q-item-section>
            </q-item>
            <q-item>
              <q-item-section>
                <q-item-label caption>Size Change</q-item-label>
                <q-item-label>
                  <q-badge
                    :color="detailData.size_delta < 0 ? 'positive' : detailData.size_delta > 0 ? 'negative' : 'grey'"
                    :label="formatSizeDelta(detailData.size_delta)"
                  />
                  <span class="q-ml-sm" v-if="detailData.source_size > 0">
                    ({{ detailSavingsPercent }}%)
                  </span>
                </q-item-label>
              </q-item-section>
              <q-item-section>
                <q-item-label caption>Size Ratio</q-item-label>
                <q-item-label>{{ detailData.size_ratio }}x</q-item-label>
              </q-item-section>
            </q-item>
            <q-separator/>
            <q-item>
              <q-item-section>
                <q-item-label caption>Start Time</q-item-label>
                <q-item-label>{{ detailData.start_time }}</q-item-label>
              </q-item-section>
              <q-item-section>
                <q-item-label caption>Finish Time</q-item-label>
                <q-item-label>{{ detailData.finish_time }}</q-item-label>
              </q-item-section>
            </q-item>
            <q-item v-if="detailData.log">
              <q-item-section>
                <q-item-label caption>Processing Log (last 20 lines)</q-item-label>
                <q-item-label>
                  <pre class="text-caption" style="max-height: 200px; overflow-y: auto; white-space: pre-wrap">{{ logTail }}</pre>
                </q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat color="positive" label="Approve" @click="approveFromDetail"/>
          <q-btn flat color="negative" label="Reject" @click="rejectFromDetail"/>
          <q-btn flat label="Close" v-close-popup/>
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Reject Confirmation Dialog -->
    <q-dialog v-model="showRejectDialog">
      <q-card>
        <q-card-section>
          <div class="text-h6">Reject {{ rejectTargetIds.length || selectedIds.length }} task(s)?</div>
        </q-card-section>
        <q-card-section>
          <q-toggle v-model="rejectRequeue" label="Requeue for re-processing instead of deleting"/>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup/>
          <q-btn
            flat
            color="negative"
            :label="rejectRequeue ? 'Requeue' : 'Delete'"
            @click="confirmReject"/>
        </q-card-actions>
      </q-card>
    </q-dialog>

  </q-page>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import axios from 'axios';

export default {
  name: 'ApprovalQueue',
  setup() {
    const tasks = ref([]);
    const selected = ref([]);
    const loading = ref(false);
    const showDetailDialog = ref(false);
    const showRejectDialog = ref(false);
    const detailData = ref(null);
    const rejectRequeue = ref(false);
    const rejectTargetIds = ref([]);
    let refreshInterval = null;

    const pagination = ref({
      page: 1,
      rowsPerPage: 25,
      rowsNumber: 0,
    });

    const columns = [
      { name: 'abspath', label: 'File', field: 'abspath', align: 'left', sortable: false },
      { name: 'source_size', label: 'Original', field: 'source_size', align: 'right', sortable: false },
      { name: 'staged_size', label: 'Transcoded', field: 'staged_size', align: 'right', sortable: false },
      { name: 'size_delta', label: 'Delta', field: 'size_delta', align: 'center', sortable: false },
      { name: 'savings', label: 'Savings', field: 'source_size', align: 'center', sortable: false },
      { name: 'finish_time', label: 'Completed', field: 'finish_time', align: 'left', sortable: false },
      { name: 'actions', label: 'Actions', field: 'id', align: 'center', sortable: false },
    ];

    const selectedIds = computed(() => selected.value.map(s => s.id));

    const logTail = computed(() => {
      if (!detailData.value || !detailData.value.log) return '';
      const lines = detailData.value.log.split('\n');
      return lines.slice(-20).join('\n');
    });

    const detailSavingsPercent = computed(() => {
      if (!detailData.value || !detailData.value.source_size) return '0';
      const pct = ((detailData.value.source_size - detailData.value.staged_size) / detailData.value.source_size) * 100;
      return pct.toFixed(1);
    });

    function fileName(abspath) {
      if (!abspath) return '';
      return abspath.split('/').pop();
    }

    function formatSize(bytes) {
      if (!bytes || bytes === 0) return '0 B';
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let i = 0;
      let size = bytes;
      while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        i++;
      }
      return size.toFixed(1) + ' ' + units[i];
    }

    function formatSizeDelta(delta) {
      if (delta === 0) return '0 B';
      const prefix = delta < 0 ? '' : '+';
      return prefix + formatSize(Math.abs(delta));
    }

    function savingsPercent(row) {
      if (!row.source_size) return '0';
      const pct = ((row.source_size - row.staged_size) / row.source_size) * 100;
      return pct.toFixed(1);
    }

    async function fetchTasks(props) {
      loading.value = true;
      const pg = props ? props.pagination : pagination.value;
      const start = (pg.page - 1) * pg.rowsPerPage;

      try {
        const res = await axios.post('/unmanic/api/v2/approval/tasks', {
          start: start,
          length: pg.rowsPerPage,
          search_value: '',
          include_library: false,
        });
        const data = res.data;
        tasks.value = data.results || [];
        pagination.value.rowsNumber = data.recordsFiltered || 0;
        pagination.value.page = pg.page;
        pagination.value.rowsPerPage = pg.rowsPerPage;
      } catch (e) {
        console.error('Failed to fetch approval tasks', e);
      } finally {
        loading.value = false;
      }
    }

    function onRequest(props) {
      fetchTasks(props);
    }

    async function approveSelected() {
      await doApprove(selectedIds.value);
    }

    async function approveSingle(id) {
      await doApprove([id]);
    }

    async function doApprove(ids) {
      try {
        await axios.post('/unmanic/api/v2/approval/approve', { id_list: ids });
        selected.value = [];
        await fetchTasks();
      } catch (e) {
        console.error('Failed to approve tasks', e);
      }
    }

    function rejectSingle(id) {
      rejectTargetIds.value = [id];
      rejectRequeue.value = false;
      showRejectDialog.value = true;
    }

    async function confirmReject() {
      const ids = rejectTargetIds.value.length > 0 ? rejectTargetIds.value : selectedIds.value;
      try {
        await axios.post('/unmanic/api/v2/approval/reject', {
          id_list: ids,
          requeue: rejectRequeue.value,
        });
        selected.value = [];
        rejectTargetIds.value = [];
        showRejectDialog.value = false;
        await fetchTasks();
      } catch (e) {
        console.error('Failed to reject tasks', e);
      }
    }

    async function showDetail(id) {
      try {
        const res = await axios.post('/unmanic/api/v2/approval/detail', { id: id });
        detailData.value = res.data;
        showDetailDialog.value = true;
      } catch (e) {
        console.error('Failed to fetch task detail', e);
      }
    }

    async function approveFromDetail() {
      if (detailData.value) {
        await doApprove([detailData.value.id]);
        showDetailDialog.value = false;
      }
    }

    function rejectFromDetail() {
      if (detailData.value) {
        rejectTargetIds.value = [detailData.value.id];
        rejectRequeue.value = false;
        showDetailDialog.value = false;
        showRejectDialog.value = true;
      }
    }

    onMounted(() => {
      fetchTasks();
      refreshInterval = setInterval(() => {
        fetchTasks();
      }, 10000);
    });

    onUnmounted(() => {
      if (refreshInterval) {
        clearInterval(refreshInterval);
      }
    });

    return {
      tasks,
      selected,
      selectedIds,
      loading,
      columns,
      pagination,
      showDetailDialog,
      showRejectDialog,
      detailData,
      rejectRequeue,
      rejectTargetIds,
      logTail,
      detailSavingsPercent,
      fileName,
      formatSize,
      formatSizeDelta,
      savingsPercent,
      fetchTasks,
      onRequest,
      approveSelected,
      approveSingle,
      rejectSingle,
      confirmReject,
      showDetail,
      approveFromDetail,
      rejectFromDetail,
    };
  },
};
</script>
