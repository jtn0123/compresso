<template>
  <div>
    <div class="row q-col-gutter-xs">
      <div class="col-6" v-for="stat in mainStats" :key="stat.key">
        <div
          class="stat-cell cursor-pointer q-pa-sm text-center"
          @click="navigateTo(stat.link)"
        >
          <q-skeleton v-if="stat.loading" type="text" width="60%" class="q-mx-auto" />
          <div v-else class="text-h6 text-weight-bold">
            {{ stat.value }}
            <q-icon v-if="stat.error" name="warning" color="negative" size="14px" class="q-ml-xs" />
          </div>
          <div class="text-caption text-grey">{{ stat.label }}</div>
        </div>
      </div>
    </div>

    <!-- Health row -->
    <div
      v-if="healthStat"
      class="stat-cell cursor-pointer q-pa-xs q-mt-xs text-center"
      @click="navigateTo('/ui/health')"
    >
      <q-skeleton v-if="healthStat.loading" type="text" width="60%" class="q-mx-auto" />
      <div v-else class="row justify-center q-gutter-xs">
        <q-badge v-if="healthStat.healthy > 0" color="positive" :label="healthStat.healthy" />
        <q-badge v-if="healthStat.warning > 0" color="warning" text-color="dark" :label="healthStat.warning" />
        <q-badge v-if="healthStat.corrupted > 0" color="negative" :label="healthStat.corrupted" />
        <span v-if="healthStat.healthy === 0 && healthStat.warning === 0 && healthStat.corrupted === 0" class="text-caption text-grey">-</span>
      </div>
      <div class="text-caption text-grey">{{ healthStat.label }}</div>
    </div>

    <!-- Approvals row (conditional) -->
    <div
      v-if="approvalStat && approvalStat.value !== '0'"
      class="stat-cell cursor-pointer q-pa-xs q-mt-xs text-center"
      @click="navigateTo('/ui/approval')"
    >
      <div class="text-subtitle1 text-weight-medium text-warning">{{ approvalStat.value }}</div>
      <div class="text-caption text-grey">{{ approvalStat.label }}</div>
    </div>

    <!-- Last updated -->
    <div v-if="lastUpdated" class="text-caption text-grey q-mt-xs text-center">
      {{ $t('common.updatedAgo', { time: relativeTime }) }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { formatBytes } from 'src/js/formatUtils'
import { useRelativeTime } from 'src/composables/useRelativeTime'

const router = useRouter()
const { t: $t } = useI18n()
const lastUpdated = ref(null)
const { relativeTime } = useRelativeTime(lastUpdated)

const compressionSummary = ref(null)
const pendingEstimate = ref(null)
const healthSummary = ref(null)
const approvalCount = ref(null)

const loading = ref({
  compression: true,
  pending: true,
  health: true,
  approval: true
})

const errors = ref({
  compression: false,
  pending: false,
  health: false,
  approval: false
})

const mainStats = computed(() => [
  {
    key: 'spaceSaved',
    label: $t('dashboardStats.spaceSaved'),
    value: compressionSummary.value ? formatBytes(compressionSummary.value.space_saved || 0) : '-',
    loading: loading.value.compression,
    error: errors.value.compression,
    link: '/ui/compression'
  },
  {
    key: 'filesProcessed',
    label: $t('dashboardStats.filesProcessed'),
    value: compressionSummary.value ? String(compressionSummary.value.file_count || 0) : '-',
    loading: loading.value.compression,
    error: errors.value.compression,
    link: '/ui/compression'
  },
  {
    key: 'avgRatio',
    label: $t('dashboardStats.avgRatio'),
    value: compressionSummary.value ? (compressionSummary.value.avg_ratio || 0).toFixed(1) + '%' : '-',
    loading: loading.value.compression,
    error: errors.value.compression,
    link: '/ui/compression'
  },
  {
    key: 'queueDepth',
    label: $t('dashboardStats.queueDepth'),
    value: pendingEstimate.value ? String(pendingEstimate.value.pending_count || 0) : '-',
    loading: loading.value.pending,
    error: errors.value.pending,
    link: '/ui/dashboard'
  }
])

const healthStat = computed(() => ({
  label: $t('dashboardStats.healthStatus'),
  healthy: healthSummary.value?.healthy || 0,
  warning: healthSummary.value?.warning || 0,
  corrupted: healthSummary.value?.corrupted || 0,
  loading: loading.value.health,
  error: errors.value.health
}))

const approvalStat = computed(() => ({
  label: $t('dashboardStats.pendingApprovals'),
  value: approvalCount.value !== null ? String(approvalCount.value) : '-',
  loading: loading.value.approval
}))

function navigateTo(path) {
  router.push(path)
}

async function fetchAll() {
  const requests = [
    axios.get(getCompressoApiUrl('v2', 'compression/summary'))
      .then(r => { compressionSummary.value = r.data; loading.value.compression = false; errors.value.compression = false })
      .catch(() => { loading.value.compression = false; errors.value.compression = true }),
    axios.get(getCompressoApiUrl('v2', 'compression/pending-estimate'))
      .then(r => { pendingEstimate.value = r.data; loading.value.pending = false; errors.value.pending = false })
      .catch(() => { loading.value.pending = false; errors.value.pending = true }),
    axios.get(getCompressoApiUrl('v2', 'healthcheck/summary'))
      .then(r => { healthSummary.value = r.data; loading.value.health = false; errors.value.health = false })
      .catch(() => { loading.value.health = false; errors.value.health = true }),
    axios.get(getCompressoApiUrl('v2', 'approval/count'))
      .then(r => { approvalCount.value = r.data.count ?? 0; loading.value.approval = false; errors.value.approval = false })
      .catch(() => { approvalCount.value = 0; loading.value.approval = false; errors.value.approval = true })
  ]
  await Promise.allSettled(requests)
  lastUpdated.value = Date.now()
}

let pollInterval = null

onMounted(() => {
  fetchAll()
  pollInterval = setInterval(fetchAll, 30000)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>

<style scoped>
.stat-cell {
  border-radius: 4px;
  transition: background-color 0.2s ease, transform 0.2s ease;
}
.stat-cell:hover {
  background-color: rgba(var(--q-primary-rgb, 25, 118, 210), 0.08);
  transform: translateY(-1px);
}
</style>
