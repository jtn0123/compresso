<template>
  <q-page class="q-pa-md">

    <!-- Header -->
    <PageHeader
      :title="$t('pages.approvalQueue.title')"
      :subtitle="$t('pages.approvalQueue.caption')"
    >
      <template #actions>
        <q-btn
          color="positive"
          icon="check_circle"
          :label="$t('pages.approvalQueue.approveSelected')"
          :disable="selectedIds.length === 0"
          :loading="approving"
          @click="approveSelected"/>
        <q-btn
          color="negative"
          icon="cancel"
          :label="$t('pages.approvalQueue.rejectSelected')"
          :disable="selectedIds.length === 0"
          @click="showRejectDialog = true"/>
        <q-btn
          flat
          icon="refresh"
          @click="fetchTasks"/>
      </template>
    </PageHeader>

    <AdmonitionBanner type="note" class="q-mb-md">
      {{ $t('pages.approvalQueue.bannerText') }}
    </AdmonitionBanner>

    <!-- New items banner -->
    <q-banner v-if="newItemCount > 0" class="bg-info text-white q-mb-md" rounded dense>
      {{ $t('pages.approvalQueue.newItemsArrived', { count: newItemCount }) }}
      <template v-slot:action>
        <q-btn flat :label="$t('pages.approvalQueue.refresh')" @click="acknowledgeNewItems"/>
      </template>
    </q-banner>

    <!-- Summary Cards -->
    <div class="row q-col-gutter-md q-mb-lg">
      <div class="col-12 col-sm-6 col-md-3">
        <q-card flat bordered class="stat-card stat-card--primary">
          <q-card-section>
            <div class="stat-label">{{ $t('pages.approvalQueue.awaitingReview') }}</div>
            <div class="stat-value">
              <q-skeleton v-if="loading && tasks.length === 0" type="text" width="40px" />
              <template v-else>{{ $t('pages.approvalQueue.filesCount', { count: pagination.rowsNumber }) }}</template>
            </div>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12 col-sm-6 col-md-3">
        <q-card flat bordered class="stat-card stat-card--positive">
          <q-card-section>
            <div class="stat-label">{{ $t('pages.approvalQueue.spaceToSave') }}</div>
            <div class="stat-value">
              <q-skeleton v-if="loading && tasks.length === 0" type="text" width="60px" />
              <template v-else>{{ formatSize(totalSpaceSaved) }}</template>
            </div>
            <div class="stat-sublabel" v-if="!loading || tasks.length > 0">{{ $t('pages.approvalQueue.ifAllApproved') }}</div>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12 col-sm-6 col-md-3">
        <q-card flat bordered class="stat-card stat-card--accent">
          <q-card-section>
            <div class="stat-label">{{ $t('pages.approvalQueue.avgSavings') }}</div>
            <div class="stat-value">
              <q-skeleton v-if="loading && tasks.length === 0" type="text" width="50px" />
              <template v-else>{{ avgSavingsPercent }}%</template>
            </div>
            <div class="stat-sublabel" v-if="!loading || tasks.length > 0">{{ $t('pages.approvalQueue.perFile') }}</div>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12 col-sm-6 col-md-3">
        <q-card flat bordered class="stat-card stat-card--info">
          <q-card-section>
            <div class="stat-label">
              {{ avgVmafScore !== null ? $t('pages.approvalQueue.avgQuality') : $t('pages.approvalQueue.largestFile') }}
            </div>
            <div class="stat-value ellipsis" style="max-width: 200px">
              <q-skeleton v-if="loading && tasks.length === 0" type="text" width="80px" />
              <template v-else-if="avgVmafScore !== null">
                <q-badge :color="vmafColor(avgVmafScore)" class="text-body1">
                  {{ avgVmafScore.toFixed(1) }}
                </q-badge>
              </template>
              <template v-else>{{ largestFileName }}</template>
            </div>
            <div class="stat-sublabel" v-if="!loading || tasks.length > 0">
              {{ avgVmafScore !== null ? $t('pages.approvalQueue.avgVmafSublabel') : largestFileSavings }}
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <!-- Tasks Table -->
    <q-table
      :rows="tasks"
      :columns="columns"
      :visible-columns="visibleColumns"
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
      <!-- Loading skeleton -->
      <template v-slot:loading>
        <q-tr v-for="n in 5" :key="'skel-' + n">
          <q-td><q-skeleton type="QCheckbox" /></q-td>
          <q-td><q-skeleton type="text" width="200px" /></q-td>
          <q-td><q-skeleton type="text" width="100px" /></q-td>
          <q-td><q-skeleton type="text" width="60px" /></q-td>
          <q-td><q-skeleton type="text" width="60px" /></q-td>
          <q-td><q-skeleton type="text" width="60px" /></q-td>
          <q-td><q-skeleton type="text" width="50px" /></q-td>
          <q-td><q-skeleton type="text" width="50px" /></q-td>
          <q-td class="gt-sm"><q-skeleton type="text" width="80px" /></q-td>
          <q-td><q-skeleton type="text" width="80px" /></q-td>
        </q-tr>
      </template>

      <!-- Row class for visual border hints -->
      <template v-slot:body="props">
        <q-tr
          :props="props"
          :class="rowBorderClass(props.row)"
        >
          <q-td auto-width>
            <q-checkbox v-model="props.selected" dense />
          </q-td>
          <!-- File name -->
          <q-td key="abspath" :props="props">
            <div class="text-weight-medium ellipsis" style="max-width: 300px">
              {{ fileName(props.row.abspath) }}
            </div>
            <div class="text-caption text-grey ellipsis" style="max-width: 300px">
              {{ props.row.abspath }}
            </div>
          </q-td>
          <!-- Codec -->
          <q-td key="codec" :props="props">
            <span v-if="props.row.source_codec && props.row.staged_codec && props.row.source_codec !== props.row.staged_codec">
              {{ props.row.source_codec }} &rarr; {{ props.row.staged_codec }}
            </span>
            <span v-else-if="props.row.source_codec">
              {{ props.row.source_codec }}
            </span>
            <span v-else class="text-grey">—</span>
            <div v-if="props.row.source_resolution && props.row.staged_resolution && props.row.source_resolution !== props.row.staged_resolution" class="text-caption text-grey">
              {{ props.row.source_resolution }} &rarr; {{ props.row.staged_resolution }}
            </div>
          </q-td>
          <!-- Original size -->
          <q-td key="source_size" :props="props" class="text-right">
            {{ formatSize(props.row.source_size) }}
          </q-td>
          <!-- Transcoded size -->
          <q-td key="staged_size" :props="props" class="text-right">
            {{ formatSize(props.row.staged_size) }}
          </q-td>
          <!-- Size delta -->
          <q-td key="size_delta" :props="props" class="text-center">
            <q-badge
              :color="props.row.size_delta < 0 ? 'positive' : props.row.size_delta > 0 ? 'negative' : 'grey'"
              :label="formatSizeDelta(props.row.size_delta)"
            />
          </q-td>
          <!-- Savings -->
          <q-td key="savings" :props="props" class="text-center">
            <span v-if="props.row.source_size > 0"
              :class="savingsNum(props.row) > 0 ? 'text-positive' : savingsNum(props.row) < 0 ? 'text-negative' : ''">
              {{ savingsPercent(props.row) }}%
            </span>
            <span v-else>—</span>
          </q-td>
          <!-- Quality (VMAF) -->
          <q-td key="quality" :props="props" class="text-center">
            <q-badge
              v-if="props.row.vmaf_score != null"
              :color="vmafColor(props.row.vmaf_score)"
              :label="props.row.vmaf_score.toFixed(1)"
            >
              <q-tooltip>
                VMAF: {{ props.row.vmaf_score.toFixed(1) }}
                <template v-if="props.row.ssim_score != null">
                  <br/>SSIM: {{ (props.row.ssim_score * 100).toFixed(1) }}%
                </template>
              </q-tooltip>
            </q-badge>
            <span v-else class="text-grey text-caption">N/A</span>
          </q-td>
          <!-- Completed -->
          <q-td key="finish_time" :props="props">
            {{ props.row.finish_time }}
          </q-td>
          <!-- Actions -->
          <q-td key="actions" :props="props" class="text-center">
            <template v-if="$q.screen.gt.xs">
              <q-btn flat dense color="positive" icon="check" size="sm" @click.stop="approveSingle(props.row.id)">
                <q-tooltip>{{ $t('pages.approvalQueue.tooltipApprove') }}</q-tooltip>
              </q-btn>
              <q-btn flat dense color="negative" icon="close" size="sm" @click.stop="rejectSingle(props.row.id)">
                <q-tooltip>{{ $t('pages.approvalQueue.tooltipReject') }}</q-tooltip>
              </q-btn>
              <q-btn flat dense color="info" icon="info" size="sm" @click.stop="showDetail(props.row.id)">
                <q-tooltip>{{ $t('pages.approvalQueue.tooltipDetails') }}</q-tooltip>
              </q-btn>
            </template>
            <template v-else>
              <q-btn flat dense icon="more_vert" size="sm">
                <q-menu>
                  <q-list dense>
                    <q-item clickable v-close-popup @click="approveSingle(props.row.id)">
                      <q-item-section avatar><q-icon name="check" color="positive"/></q-item-section>
                      <q-item-section>{{ $t('pages.approvalQueue.tooltipApprove') }}</q-item-section>
                    </q-item>
                    <q-item clickable v-close-popup @click="rejectSingle(props.row.id)">
                      <q-item-section avatar><q-icon name="close" color="negative"/></q-item-section>
                      <q-item-section>{{ $t('pages.approvalQueue.tooltipReject') }}</q-item-section>
                    </q-item>
                    <q-item clickable v-close-popup @click="showDetail(props.row.id)">
                      <q-item-section avatar><q-icon name="info" color="info"/></q-item-section>
                      <q-item-section>{{ $t('pages.approvalQueue.tooltipDetails') }}</q-item-section>
                    </q-item>
                  </q-list>
                </q-menu>
              </q-btn>
            </template>
          </q-td>
        </q-tr>
      </template>

      <!-- No data — context-aware empty state -->
      <template v-slot:no-data>
        <div class="full-width column items-center q-pa-lg text-grey">
          <q-icon name="check_circle_outline" size="3rem" class="q-mb-sm"/>
          <template v-if="approvalEnabled === true">
            <div class="text-h6">{{ $t('pages.approvalQueue.allClear') }}</div>
            <div class="text-caption">
              {{ $t('pages.approvalQueue.allClearCaption') }}
            </div>
          </template>
          <template v-else-if="approvalEnabled === false">
            <div class="text-h6">{{ $t('pages.approvalQueue.approvalModeOff') }}</div>
            <div class="text-caption q-mb-sm">
              {{ $t('pages.approvalQueue.filesReplacedAutomatically') }}
            </div>
            <q-btn
              flat
              color="primary"
              :label="$t('pages.approvalQueue.enableInLibrarySettings')"
              icon="settings"
              to="/ui/settings-library"
            />
          </template>
          <template v-else>
            <div class="text-h6">{{ $t('pages.approvalQueue.noTasksAwaiting') }}</div>
            <div class="text-caption">
              {{ $t('pages.approvalQueue.transcodedFilesWillAppear') }}
            </div>
          </template>
        </div>
      </template>
    </q-table>

    <!-- Detail Dialog -->
    <q-dialog
      v-model="showDetailDialog"
      persistent
      :maximized="$q.screen.lt.md"
      :full-width="previewActive"
    >
      <q-card :style="previewActive ? 'max-width: 1200px; width: 100%' : 'min-width: 500px; max-width: 700px'">
        <!-- Header: file name -->
        <q-card-section>
          <div class="text-h6 ellipsis" v-if="detailData">{{ fileName(detailData.abspath) }}</div>
          <div class="text-caption text-grey ellipsis" v-if="detailData">{{ detailData.abspath }}</div>
          <q-skeleton v-else type="text" />
        </q-card-section>

        <q-card-section v-if="detailData">
          <!-- Section 1: What Changed -->
          <div class="text-subtitle2 q-mb-sm">{{ $t('pages.approvalQueue.whatChanged') }}</div>
          <div class="row q-col-gutter-md q-mb-md">
            <div class="col-12 col-sm-6">
              <q-card flat bordered class="bg-grey-2">
                <q-card-section class="q-pa-sm">
                  <div class="text-caption text-weight-bold">{{ $t('pages.approvalQueue.original') }}</div>
                  <div class="row q-gutter-xs q-mt-xs">
                    <q-badge v-if="detailData.source_codec" color="grey-7">{{ detailData.source_codec }}</q-badge>
                    <q-badge v-if="detailData.source_resolution" color="grey-7">{{ detailData.source_resolution }}</q-badge>
                    <q-badge v-if="detailData.source_container" color="grey-7">.{{ detailData.source_container }}</q-badge>
                  </div>
                  <div class="text-body1 q-mt-xs">{{ formatSize(detailData.source_size) }}</div>
                </q-card-section>
              </q-card>
            </div>
            <div class="col-12 col-sm-6">
              <q-card flat bordered class="bg-grey-2">
                <q-card-section class="q-pa-sm">
                  <div class="text-caption text-weight-bold">{{ $t('pages.approvalQueue.transcoded') }}</div>
                  <div class="row q-gutter-xs q-mt-xs">
                    <q-badge v-if="detailData.staged_codec" color="grey-7">{{ detailData.staged_codec }}</q-badge>
                    <q-badge v-if="detailData.staged_resolution" color="grey-7">{{ detailData.staged_resolution }}</q-badge>
                    <q-badge v-if="detailData.staged_container" color="grey-7">.{{ detailData.staged_container }}</q-badge>
                  </div>
                  <div class="text-body1 q-mt-xs">{{ formatSize(detailData.staged_size) }}</div>
                </q-card-section>
              </q-card>
            </div>
          </div>
          <!-- Savings summary -->
          <div class="text-center q-mb-md">
            <span
              v-if="detailData.size_delta < 0"
              class="text-h6 text-positive"
            >
              {{ $t('pages.approvalQueue.spaceSavedDetail', { size: formatSize(Math.abs(detailData.size_delta)), percent: detailSavingsPercent }) }}
            </span>
            <span
              v-else-if="detailData.size_delta > 0"
              class="text-h6 text-negative"
            >
              {{ $t('pages.approvalQueue.fileBiggerBy', { size: formatSize(detailData.size_delta), percent: detailSavingsPercent }) }}
            </span>
            <span v-else class="text-h6 text-grey">{{ $t('pages.approvalQueue.noSizeChange') }}</span>
          </div>

          <!-- Section 2: Quality Scores -->
          <div v-if="detailData.vmaf_score != null || detailData.ssim_score != null" class="q-mb-md">
            <div class="text-subtitle2 q-mb-sm">{{ $t('pages.approvalQueue.qualityScores') }}</div>
            <div class="row q-gutter-md">
              <div v-if="detailData.vmaf_score != null" class="col-auto">
                <q-badge
                  :color="vmafColor(detailData.vmaf_score)"
                  class="text-body2 q-pa-sm"
                >
                  VMAF: {{ detailData.vmaf_score.toFixed(1) }}
                </q-badge>
                <div class="text-caption text-grey q-mt-xs">
                  {{ vmafLabel(detailData.vmaf_score) }}
                </div>
              </div>
              <div v-if="detailData.ssim_score != null" class="col-auto">
                <q-badge
                  color="info"
                  class="text-body2 q-pa-sm"
                >
                  SSIM: {{ (detailData.ssim_score * 100).toFixed(1) }}%
                </q-badge>
                <div class="text-caption text-grey q-mt-xs">
                  {{ $t('pages.approvalQueue.ssimExplainer') }}
                </div>
              </div>
            </div>
          </div>

          <!-- Section 3: Processing Info (collapsed) -->
          <q-expansion-item
            :label="$t('pages.approvalQueue.processingInfo')"
            icon="schedule"
            header-class="text-subtitle2"
            default-closed
            class="q-mb-md"
          >
            <q-card flat>
              <q-card-section class="q-pa-sm">
                <div class="row q-gutter-md">
                  <div class="col">
                    <div class="text-caption">{{ $t('pages.approvalQueue.startTime') }}</div>
                    <div>{{ detailData.start_time }}</div>
                  </div>
                  <div class="col">
                    <div class="text-caption">{{ $t('pages.approvalQueue.finishTime') }}</div>
                    <div>{{ detailData.finish_time }}</div>
                  </div>
                </div>
                <div class="row q-gutter-md q-mt-sm">
                  <div class="col">
                    <div class="text-caption">{{ $t('pages.approvalQueue.sizeRatio') }}</div>
                    <div>{{ detailData.size_ratio }}x</div>
                  </div>
                </div>
                <div v-if="detailData.log" class="q-mt-md">
                  <q-expansion-item :label="$t('pages.approvalQueue.processingLog')" dense default-closed>
                    <pre class="text-caption" style="max-height: 200px; overflow-y: auto; white-space: pre-wrap">{{ logTail }}</pre>
                  </q-expansion-item>
                </div>
              </q-card-section>
            </q-card>
          </q-expansion-item>

          <!-- Section 4: Quality Preview -->
          <div class="q-mb-md">
            <q-btn
              v-if="!previewActive && !previewLoading"
              color="info"
              icon="compare"
              :label="$t('pages.approvalQueue.compareQuality')"
              outline
              @click="startPreview"
            />
            <div class="text-caption text-grey q-mt-xs" v-if="!previewActive && !previewLoading">
              {{ $t('pages.approvalQueue.previewCaption') }}
            </div>
            <div v-if="previewLoading" class="q-pa-md text-center">
              <q-spinner color="primary" size="2em" class="q-mr-sm"/>
              {{ $t('pages.approvalQueue.generatingPreview', { status: previewStatus }) }}
            </div>
            <div v-if="previewActive && previewData">
              <VideoCompare
                :sourceUrl="previewData.source_url"
                :encodedUrl="previewData.encoded_url"
                :sourceSize="previewData.source_size || 0"
                :encodedSize="previewData.encoded_size || 0"
                :sourceCodec="previewData.source_codec || ''"
                :encodedCodec="previewData.encoded_codec || ''"
                :vmafScore="previewData.vmaf_score"
                :ssimScore="previewData.ssim_score"
              />
            </div>
          </div>
        </q-card-section>

        <!-- Skeleton while loading detail -->
        <q-card-section v-else>
          <q-skeleton type="text" class="q-mb-sm" />
          <q-skeleton type="rect" height="100px" class="q-mb-sm" />
          <q-skeleton type="text" />
        </q-card-section>

        <!-- Action buttons -->
        <q-card-actions class="q-pa-md">
          <q-btn
            color="positive"
            icon="check_circle"
            :label="$t('pages.approvalQueue.approve')"
            :loading="approving"
            class="col"
            @click="approveFromDetail"/>
          <q-btn
            color="negative"
            icon="cancel"
            :label="$t('pages.approvalQueue.reject')"
            class="col"
            @click="rejectFromDetail"/>
          <q-btn
            flat
            :label="$t('pages.approvalQueue.close')"
            class="col-auto"
            @click="closeDetail"/>
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Reject Confirmation Dialog -->
    <q-dialog v-model="showRejectDialog">
      <q-card style="min-width: 400px">
        <q-card-section>
          <div class="text-h6">{{ $t('pages.approvalQueue.rejectTitle', { count: rejectTargetIds.length || selectedIds.length }) }}</div>
        </q-card-section>
        <q-card-section>
          <div class="text-subtitle2 q-mb-sm">{{ $t('pages.approvalQueue.whatHappensToRejected') }}</div>
          <q-option-group
            v-model="rejectAction"
            :options="rejectOptions"
            type="radio"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat :label="$t('pages.approvalQueue.cancel')" v-close-popup/>
          <q-btn
            flat
            color="negative"
            :label="$t('pages.approvalQueue.reject')"
            :loading="rejecting"
            @click="confirmReject"/>
        </q-card-actions>
      </q-card>
    </q-dialog>

  </q-page>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';
import axios from 'axios';
import { getCompressoApiUrl } from 'src/js/compressoGlobals';
import VideoCompare from 'components/preview/VideoCompare.vue';
import AdmonitionBanner from 'components/ui/AdmonitionBanner.vue';
import PageHeader from 'components/ui/PageHeader.vue';

export default {
  name: 'ApprovalQueue',
  components: { VideoCompare, AdmonitionBanner, PageHeader },
  setup() {
    const $q = useQuasar();
    const { t: $t } = useI18n();
    const tasks = ref([]);
    const selected = ref([]);
    const loading = ref(false);
    const approving = ref(false);
    const rejecting = ref(false);
    const showDetailDialog = ref(false);
    const showRejectDialog = ref(false);
    const detailData = ref(null);
    const rejectAction = ref('discard');
    const rejectTargetIds = ref([]);
    const approvalEnabled = ref(null);
    const newItemCount = ref(0);
    const allTasks = ref([]);  // All tasks for summary cards (not just current page)
    let lastKnownIds = new Set();
    let refreshInterval = null;

    // Preview state
    const previewActive = ref(false);
    const previewLoading = ref(false);
    const previewStatus = ref('');
    const previewData = ref(null);
    let previewJobId = null;
    let previewPollInterval = null;

    const pagination = ref({
      page: 1,
      rowsPerPage: 25,
      rowsNumber: 0,
    });

    const columns = computed(() => [
      { name: 'abspath', label: $t('pages.approvalQueue.columnFile'), field: 'abspath', align: 'left', sortable: false },
      { name: 'codec', label: $t('pages.approvalQueue.columnCodec'), field: 'source_codec', align: 'left', sortable: false },
      { name: 'source_size', label: $t('pages.approvalQueue.columnOriginal'), field: 'source_size', align: 'right', sortable: false },
      { name: 'staged_size', label: $t('pages.approvalQueue.columnNew'), field: 'staged_size', align: 'right', sortable: false },
      { name: 'size_delta', label: $t('pages.approvalQueue.columnChange'), field: 'size_delta', align: 'center', sortable: false },
      { name: 'savings', label: $t('pages.approvalQueue.columnSpaceSaved'), field: 'source_size', align: 'center', sortable: false },
      { name: 'quality', label: $t('pages.approvalQueue.columnQuality'), field: 'vmaf_score', align: 'center', sortable: false },
      { name: 'finish_time', label: $t('pages.approvalQueue.columnCompleted'), field: 'finish_time', align: 'left', sortable: false },
      { name: 'actions', label: $t('pages.approvalQueue.columnActions'), field: 'id', align: 'center', sortable: false },
    ]);

    const selectedIds = computed(() => selected.value.map(s => s.id));

    const visibleColumns = computed(() => {
      const all = columns.value.map(c => c.name);
      if ($q.screen.lt.md) {
        return all.filter(n => n !== 'finish_time');
      }
      return all;
    });

    const logTail = computed(() => {
      if (!detailData.value || !detailData.value.log) return '';
      const lines = detailData.value.log.split('\n');
      return lines.slice(-20).join('\n');
    });

    const detailSavingsPercent = computed(() => {
      if (!detailData.value || !detailData.value.source_size) return '0';
      const pct = ((detailData.value.source_size - detailData.value.staged_size) / detailData.value.source_size) * 100;
      return Math.abs(pct).toFixed(1);
    });

    const rejectOptions = computed(() => [
      { label: $t('pages.approvalQueue.discardOption'), value: 'discard' },
      { label: $t('pages.approvalQueue.requeueOption'), value: 'requeue' },
    ]);

    // Summary card computations (use allTasks so they reflect the full queue, not just current page)
    const totalSpaceSaved = computed(() => {
      return allTasks.value.reduce((sum, t) => {
        const delta = t.size_delta || 0;
        return delta < 0 ? sum + Math.abs(delta) : sum;
      }, 0);
    });

    const avgSavingsPercent = computed(() => {
      const valid = allTasks.value.filter(t => t.source_size > 0);
      if (valid.length === 0) return '0.0';
      const totalPct = valid.reduce((sum, t) => {
        return sum + ((t.source_size - t.staged_size) / t.source_size) * 100;
      }, 0);
      return (totalPct / valid.length).toFixed(1);
    });

    const largestFileName = computed(() => {
      if (allTasks.value.length === 0) return '—';
      let largest = allTasks.value[0];
      for (const t of allTasks.value) {
        if (Math.abs(t.size_delta || 0) > Math.abs(largest.size_delta || 0)) {
          largest = t;
        }
      }
      return fileName(largest.abspath);
    });

    const largestFileSavings = computed(() => {
      if (allTasks.value.length === 0) return '';
      let largest = allTasks.value[0];
      for (const t of allTasks.value) {
        if (Math.abs(t.size_delta || 0) > Math.abs(largest.size_delta || 0)) {
          largest = t;
        }
      }
      return formatSize(Math.abs(largest.size_delta || 0)) + ' ' + $t('pages.approvalQueue.saved');
    });

    function fileName(abspath) {
      if (!abspath) return '';
      return abspath.split('/').pop();
    }

    function formatSize(bytes) {
      if (!bytes || bytes === 0) return '0 B';
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let i = 0;
      let size = Math.abs(bytes);
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

    function savingsNum(row) {
      if (!row.source_size) return 0;
      return ((row.source_size - row.staged_size) / row.source_size) * 100;
    }

    function savingsPercent(row) {
      return savingsNum(row).toFixed(1);
    }

    function rowBorderClass(row) {
      if (row.size_delta > 0) return 'row-border-negative';
      if (row.source_size > 0 && ((row.source_size - row.staged_size) / row.source_size) > 0.2) return 'row-border-positive';
      return '';
    }

    function vmafColor(score) {
      if (score == null) return 'grey';
      if (score >= 90) return 'positive';
      if (score >= 70) return 'warning';
      return 'negative';
    }

    function vmafLabel(score) {
      if (score == null) return '';
      if (score >= 90) return $t('pages.approvalQueue.qualityExcellent');
      if (score >= 70) return $t('pages.approvalQueue.qualityGood');
      return $t('pages.approvalQueue.qualityPoor');
    }

    const avgVmafScore = computed(() => {
      const withVmaf = allTasks.value.filter(t => t.vmaf_score != null);
      if (withVmaf.length === 0) return null;
      const sum = withVmaf.reduce((acc, t) => acc + t.vmaf_score, 0);
      return sum / withVmaf.length;
    });

    async function fetchApprovalSetting() {
      try {
        const res = await axios.get(getCompressoApiUrl('v2', 'settings/read'));
        approvalEnabled.value = res.data.settings.approval_required === true || res.data.settings.approval_required === 'true';
      } catch {
        // ignore
      }
    }

    async function fetchAllTasksForSummary() {
      try {
        const res = await axios.post(getCompressoApiUrl('v2', 'approval/tasks'), {
          start: 0,
          length: 1000,
          search_value: '',
          include_library: false,
        });
        allTasks.value = res.data.results || [];
      } catch {
        // Summary cards will just show current page data as fallback
      }
    }

    async function fetchTasks(props) {
      loading.value = true;
      const pg = props ? props.pagination : pagination.value;
      const start = (pg.page - 1) * pg.rowsPerPage;

      try {
        const res = await axios.post(getCompressoApiUrl('v2', 'approval/tasks'), {
          start: start,
          length: pg.rowsPerPage,
          search_value: '',
          include_library: false,
        });
        const data = res.data;
        const newTasks = data.results || [];
        const newCount = data.recordsFiltered || 0;

        // Smart refresh: detect new items
        const newIds = new Set(newTasks.map(t => t.id));
        if (lastKnownIds.size > 0) {
          let addedCount = 0;
          for (const id of newIds) {
            if (!lastKnownIds.has(id)) addedCount++;
          }
          if (addedCount > 0 && tasks.value.length > 0) {
            newItemCount.value += addedCount;
          }
        }

        // Preserve selection across refresh
        const selectedIdSet = new Set(selectedIds.value);
        tasks.value = newTasks;
        lastKnownIds = newIds;
        pagination.value.rowsNumber = newCount;
        pagination.value.page = pg.page;
        pagination.value.rowsPerPage = pg.rowsPerPage;

        // Restore selection
        selected.value = newTasks.filter(t => selectedIdSet.has(t.id));
      } catch (e) {
        $q.notify({ type: 'negative', message: $t('pages.approvalQueue.failedToFetchTasks'), timeout: 3000, position: 'top' });
      } finally {
        loading.value = false;
      }
    }

    function acknowledgeNewItems() {
      newItemCount.value = 0;
      fetchTasks();
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
      approving.value = true;
      try {
        await axios.post(getCompressoApiUrl('v2', 'approval/approve'), { id_list: ids });
        $q.notify({ type: 'positive', message: $t('pages.approvalQueue.approvedCount', { count: ids.length }), timeout: 3000, position: 'top' });
        selected.value = [];
        await fetchTasks();
      } catch (e) {
        $q.notify({ type: 'negative', message: $t('pages.approvalQueue.failedToApprove'), timeout: 3000, position: 'top' });
      } finally {
        approving.value = false;
      }
    }

    function rejectSingle(id) {
      rejectTargetIds.value = [id];
      rejectAction.value = 'discard';
      showRejectDialog.value = true;
    }

    async function confirmReject() {
      const ids = rejectTargetIds.value.length > 0 ? rejectTargetIds.value : selectedIds.value;
      rejecting.value = true;
      try {
        await axios.post(getCompressoApiUrl('v2', 'approval/reject'), {
          id_list: ids,
          requeue: rejectAction.value === 'requeue',
        });
        $q.notify({ type: 'positive', message: $t('pages.approvalQueue.rejectedCount', { count: ids.length }), timeout: 3000, position: 'top' });
        selected.value = [];
        rejectTargetIds.value = [];
        showRejectDialog.value = false;
        await fetchTasks();
      } catch (e) {
        $q.notify({ type: 'negative', message: $t('pages.approvalQueue.failedToReject'), timeout: 3000, position: 'top' });
      } finally {
        rejecting.value = false;
      }
    }

    async function showDetail(id) {
      detailData.value = null;
      previewActive.value = false;
      previewLoading.value = false;
      previewData.value = null;
      showDetailDialog.value = true;
      try {
        const res = await axios.post(getCompressoApiUrl('v2', 'approval/detail'), { id: id });
        detailData.value = res.data;
      } catch (e) {
        $q.notify({ type: 'negative', message: $t('pages.approvalQueue.failedToFetchDetail'), timeout: 3000, position: 'top' });
        showDetailDialog.value = false;
      }
    }

    async function approveFromDetail() {
      if (detailData.value) {
        await doApprove([detailData.value.id]);
        closeDetail();
      }
    }

    function rejectFromDetail() {
      if (detailData.value) {
        rejectTargetIds.value = [detailData.value.id];
        rejectAction.value = 'discard';
        showDetailDialog.value = false;
        cleanupPreview();
        showRejectDialog.value = true;
      }
    }

    function closeDetail() {
      showDetailDialog.value = false;
      cleanupPreview();
    }

    // Preview functions
    async function startPreview() {
      if (!detailData.value) return;
      previewLoading.value = true;
      previewStatus.value = 'Starting...';
      try {
        const res = await axios.post(getCompressoApiUrl('v2', 'preview/create'), {
          source_path: detailData.value.abspath,
          start_time: 0,
          duration: 10,
          library_id: detailData.value.library_id || 1,
        });
        previewJobId = res.data.job_id;
        previewStatus.value = 'Processing...';
        pollPreviewStatus();
      } catch (e) {
        previewLoading.value = false;
        $q.notify({ type: 'negative', message: $t('pages.approvalQueue.failedToCreatePreview'), timeout: 3000, position: 'top' });
      }
    }

    function pollPreviewStatus() {
      previewPollInterval = setInterval(async () => {
        try {
          const res = await axios.post(getCompressoApiUrl('v2', 'preview/status'), { job_id: previewJobId });
          const status = res.data.status;
          previewStatus.value = status;
          if (status === 'complete') {
            clearInterval(previewPollInterval);
            previewPollInterval = null;
            previewData.value = res.data;
            previewLoading.value = false;
            previewActive.value = true;
          } else if (status === 'error' || status === 'failed') {
            clearInterval(previewPollInterval);
            previewPollInterval = null;
            previewLoading.value = false;
            $q.notify({ type: 'negative', message: $t('pages.approvalQueue.previewFailed', { error: res.data.error || '' }), timeout: 3000, position: 'top' });
          }
        } catch {
          clearInterval(previewPollInterval);
          previewPollInterval = null;
          previewLoading.value = false;
        }
      }, 2000);
    }

    async function cleanupPreview() {
      if (previewPollInterval) {
        clearInterval(previewPollInterval);
        previewPollInterval = null;
      }
      if (previewJobId) {
        try {
          await axios.post(getCompressoApiUrl('v2', 'preview/cleanup'), { job_id: previewJobId });
        } catch {
          // ignore cleanup errors
        }
        previewJobId = null;
      }
      previewActive.value = false;
      previewLoading.value = false;
      previewData.value = null;
    }

    onMounted(() => {
      fetchApprovalSetting();
      fetchTasks();
      fetchAllTasksForSummary();
      refreshInterval = setInterval(() => {
        fetchTasks();
        fetchAllTasksForSummary();
      }, 10000);
    });

    onUnmounted(() => {
      if (refreshInterval) {
        clearInterval(refreshInterval);
      }
      cleanupPreview();
    });

    return {
      tasks,
      selected,
      selectedIds,
      loading,
      approving,
      rejecting,
      columns,
      visibleColumns,
      pagination,
      showDetailDialog,
      showRejectDialog,
      detailData,
      rejectAction,
      rejectTargetIds,
      rejectOptions,
      logTail,
      detailSavingsPercent,
      approvalEnabled,
      newItemCount,
      totalSpaceSaved,
      avgSavingsPercent,
      largestFileName,
      largestFileSavings,
      avgVmafScore,
      vmafColor,
      vmafLabel,
      previewActive,
      previewLoading,
      previewStatus,
      previewData,
      fileName,
      formatSize,
      formatSizeDelta,
      savingsNum,
      savingsPercent,
      rowBorderClass,
      fetchTasks,
      acknowledgeNewItems,
      onRequest,
      approveSelected,
      approveSingle,
      rejectSingle,
      confirmReject,
      showDetail,
      approveFromDetail,
      rejectFromDetail,
      closeDetail,
      startPreview,
    };
  },
};
</script>

<style scoped>
.row-border-negative {
  border-left: 3px solid rgba(255, 0, 0, 0.3);
}
.row-border-positive {
  border-left: 3px solid rgba(0, 200, 0, 0.3);
}
</style>
