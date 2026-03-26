<template>
  <q-card flat bordered>
    <q-expansion-item
      :label="$t('healthCheckPanel.title')"
      :caption="lastUpdated ? $t('common.updatedAgo', { time: relativeTime }) : ''"
      icon="health_and_safety"
      header-class="bg-card-head text-primary"
      :default-opened="isScanning"
    >
      <q-card-section>
        <!-- Scan progress -->
        <div v-if="isScanning" class="q-mb-sm">
          <div class="row items-center q-gutter-sm q-mb-xs">
            <q-badge color="positive" :label="$t('healthCheckPanel.scanning')" />
            <span class="text-caption">
              {{ scanProgress.checked || 0 }}/{{ scanProgress.total || 0 }}
              ({{ scanPercent }}%)
            </span>
          </div>
          <q-linear-progress :value="scanPercent / 100" size="8px" color="positive" :track-color="$q.dark.isActive ? 'grey-8' : 'grey-4'" />
        </div>
        <div v-else class="q-mb-sm">
          <q-badge color="grey" :label="$t('healthCheckPanel.notScanning')" />
        </div>

        <!-- Worker count control -->
        <div class="row items-center q-gutter-sm q-mb-sm">
          <span class="text-caption text-grey">{{ $t('healthCheckPanel.workers') }}:</span>
          <q-btn dense flat round size="sm" icon="remove" @click="changeWorkerCount(-1)" :disable="workerCount <= 0" />
          <span class="text-weight-medium">{{ workerCount }}</span>
          <q-btn dense flat round size="sm" icon="add" @click="changeWorkerCount(1)" />
        </div>

        <!-- Health summary -->
        <div v-if="fetchError" class="text-caption text-negative q-mb-sm">
          <q-icon name="warning" class="q-mr-xs" />
          {{ $t('healthCheckPanel.fetchError') }}
        </div>
        <div v-else-if="!isScanning && !summary.healthy && !summary.warning && !summary.corrupted" class="text-caption text-grey q-mb-sm">
          {{ $t('healthCheckPanel.noData') }}
        </div>
        <div v-else class="row q-gutter-sm">
          <q-badge color="positive" :label="(summary.healthy || 0) + ' healthy'" />
          <q-badge v-if="summary.warning > 0" color="warning" text-color="dark" :label="summary.warning + ' warning'" />
          <q-badge v-if="summary.corrupted > 0" color="negative" :label="summary.corrupted + ' corrupted'" />
        </div>

        <div class="q-mt-sm">
          <router-link to="/ui/health" class="text-primary text-caption">
            {{ $t('healthCheckPanel.viewDetails') }} →
          </router-link>
        </div>
      </q-card-section>
    </q-expansion-item>
  </q-card>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { useRelativeTime } from 'src/composables/useRelativeTime'

const $q = useQuasar()
const { t: $t } = useI18n()

const lastUpdated = ref(null)
const { relativeTime } = useRelativeTime(lastUpdated)

const summary = ref({})
const workerCount = ref(0)
const isScanning = ref(false)
const scanProgress = ref({})
const fetchError = ref(false)

const scanPercent = computed(() => {
  if (!scanProgress.value.total || scanProgress.value.total === 0) return 0
  return Math.round((scanProgress.value.checked / scanProgress.value.total) * 100)
})

async function fetchData() {
  try {
    const [summaryRes, workersRes] = await Promise.all([
      axios.get(getCompressoApiUrl('v2', 'healthcheck/summary')),
      axios.get(getCompressoApiUrl('v2', 'healthcheck/workers'))
    ])
    summary.value = summaryRes.data
    isScanning.value = summaryRes.data.scanning || false
    scanProgress.value = {
      checked: summaryRes.data.scan_progress?.checked || 0,
      total: summaryRes.data.scan_progress?.total || 0
    }
    workerCount.value = workersRes.data.worker_count || 0
    fetchError.value = false
    lastUpdated.value = Date.now()
  } catch (_e) {
    fetchError.value = true
  }
}

async function changeWorkerCount(delta) {
  const newCount = Math.max(0, workerCount.value + delta)
  try {
    await axios.post(getCompressoApiUrl('v2', 'healthcheck/workers'), { worker_count: newCount })
    workerCount.value = newCount
  } catch (_e) {
    $q.notify({
      color: 'negative',
      position: 'top',
      message: $t('healthCheckPanel.workerCountFailed'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }]
    })
  }
}

let pollInterval = null

onMounted(() => {
  fetchData()
  pollInterval = setInterval(fetchData, 10000)
})

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval)
  }
})
</script>
