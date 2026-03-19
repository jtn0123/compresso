<template>
  <div class="row q-col-gutter-sm">
    <div class="col-6 col-sm-4 col-md-2" v-for="stat in visibleStats" :key="stat.key">
      <q-card
        flat
        bordered
        class="cursor-pointer stat-card"
        @click="navigateTo(stat.link)"
      >
        <q-card-section class="q-pa-sm text-center">
          <div class="text-caption text-grey">{{ stat.label }}</div>
          <q-skeleton v-if="stat.loading" type="text" width="60%" class="q-mx-auto" />
          <template v-else>
            <div v-if="stat.key === 'health'" class="row justify-center q-gutter-xs q-mt-xs">
              <q-badge v-if="stat.healthy > 0" color="positive" :label="stat.healthy" />
              <q-badge v-if="stat.warning > 0" color="warning" text-color="dark" :label="stat.warning" />
              <q-badge v-if="stat.corrupted > 0" color="negative" :label="stat.corrupted" />
              <span v-if="stat.healthy === 0 && stat.warning === 0 && stat.corrupted === 0" class="text-subtitle1 text-weight-medium">
                -
                <q-icon v-if="stat.error" name="warning" color="negative" size="14px" class="q-ml-xs" />
              </span>
            </div>
            <div v-else class="text-subtitle1 text-weight-medium">
              {{ stat.value }}
              <q-icon v-if="stat.error" name="warning" color="negative" size="14px" class="q-ml-xs" />
            </div>
          </template>
        </q-card-section>
      </q-card>
    </div>
  </div>
  <div v-if="isStale" class="q-mt-xs">
    <q-banner dense class="bg-warning text-dark text-caption" rounded>
      <template v-slot:avatar>
        <q-icon name="warning" color="dark" />
      </template>
      {{ $t('common.dataStale') }} — {{ $t('common.updatedAgo', { time: relativeTime }) }}
    </q-banner>
  </div>
  <div v-else-if="lastUpdated" class="text-caption text-grey q-mt-xs text-center">
    {{ $t('common.updatedAgo', { time: relativeTime }) }}
    <q-tooltip>{{ lastUpdatedExact }}</q-tooltip>
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
const { t } = useI18n()
const lastUpdated = ref(null)
const { relativeTime } = useRelativeTime(lastUpdated)
const lastUpdatedExact = computed(() => lastUpdated.value ? new Date(lastUpdated.value).toLocaleString() : '')
const isStale = computed(() => {
  if (!lastUpdated.value) return false
  const hasError = errors.value.compression || errors.value.pending || errors.value.health
  return hasError && (Date.now() - lastUpdated.value) > 60000
})

const compressionSummary = ref(null)
const pendingEstimate = ref(null)
const healthSummary = ref(null)
const approvalCount = ref(null)
const optimizationProgress = ref(null)

const loading = ref({
  compression: true,
  pending: true,
  health: true,
  approval: true,
  optimization: true
})

const errors = ref({
  compression: false,
  pending: false,
  health: false,
  approval: false,
  optimization: false
})

const stats = computed(() => [
  {
    key: 'spaceSaved',
    label: t('dashboardStats.spaceSaved'),
    value: compressionSummary.value ? formatBytes(compressionSummary.value.space_saved || 0) : '-',
    loading: loading.value.compression,
    error: errors.value.compression,
    link: '/ui/compression'
  },
  {
    key: 'filesProcessed',
    label: t('dashboardStats.filesProcessed'),
    value: compressionSummary.value ? String(compressionSummary.value.file_count || 0) : '-',
    loading: loading.value.compression,
    error: errors.value.compression,
    link: '/ui/compression'
  },
  {
    key: 'avgRatio',
    label: t('dashboardStats.avgRatio'),
    value: compressionSummary.value ? (compressionSummary.value.avg_ratio || 0).toFixed(1) + '%' : '-',
    loading: loading.value.compression,
    error: errors.value.compression,
    link: '/ui/compression'
  },
  {
    key: 'queueDepth',
    label: t('dashboardStats.queueDepth'),
    value: pendingEstimate.value ? String(pendingEstimate.value.pending_count || 0) : '-',
    loading: loading.value.pending,
    error: errors.value.pending,
    link: '/ui/dashboard'
  },
  {
    key: 'health',
    label: t('dashboardStats.healthStatus'),
    healthy: healthSummary.value?.healthy || 0,
    warning: healthSummary.value?.warning || 0,
    corrupted: healthSummary.value?.corrupted || 0,
    loading: loading.value.health,
    error: errors.value.health,
    link: '/ui/health'
  },
  {
    key: 'approvals',
    label: t('dashboardStats.pendingApprovals'),
    value: approvalCount.value !== null ? String(approvalCount.value) : '-',
    loading: loading.value.approval,
    error: errors.value.approval,
    link: '/ui/approval'
  },
  {
    key: 'optimization',
    label: t('flow.optimizationProgress'),
    value: optimizationProgress.value ? optimizationProgress.value.percent + '%' : '-',
    loading: loading.value.optimization,
    error: errors.value.optimization,
    link: '/ui/compression'
  }
])

const visibleStats = computed(() => {
  return stats.value.filter(s => {
    if (s.key === 'approvals' && !s.loading && approvalCount.value === 0) {
      return false
    }
    if (s.key === 'optimization' && !s.loading && (!optimizationProgress.value || optimizationProgress.value.percent === 0)) {
      return false
    }
    return true
  })
})

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
      .catch(() => { approvalCount.value = 0; loading.value.approval = false; errors.value.approval = true }),
    axios.get(getCompressoApiUrl('v2', 'compression/optimization-progress'))
      .then(r => { optimizationProgress.value = r.data; loading.value.optimization = false; errors.value.optimization = false })
      .catch(() => { loading.value.optimization = false; errors.value.optimization = true })
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
  if (pollInterval) {
    clearInterval(pollInterval)
  }
})
</script>

<style scoped>
.stat-card {
  transition: background-color 0.2s;
}
.stat-card:hover {
  background-color: rgba(var(--q-primary-rgb, 25, 118, 210), 0.08);
}
</style>
