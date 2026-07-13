<template>
  <q-banner v-if="pauseRequired" data-testid="global-safety-banner" class="bg-negative text-white" dense>
    <template #avatar><q-icon name="report_problem" /></template>
    {{ $t('pages.deploymentReadiness.globalPause') }}
    <template #action>
      <q-btn flat color="white" :label="$t('pages.deploymentReadiness.reviewSafety')" to="/ui/readiness" />
    </template>
  </q-banner>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'

const pauseRequired = ref(false)
let intervalId

async function refresh() {
  try {
    const response = await axios.get(getCompressoApiUrl('v2', 'system/safety'))
    pauseRequired.value = Boolean(response.data.pause_required)
  } catch {
    // Keep the last known state; the connection indicator already reports API loss.
  }
}

onMounted(() => {
  refresh()
  intervalId = globalThis.setInterval(refresh, 15000)
})
onUnmounted(() => globalThis.clearInterval(intervalId))
</script>
