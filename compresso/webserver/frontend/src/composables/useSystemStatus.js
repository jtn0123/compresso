import { ref } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'

/**
 * Composable for system status data.
 * Provides static system info (fetched once via API) and live metrics (updated via WebSocket).
 */
export function useSystemStatus() {
  const systemInfo = ref(null)
  const liveMetrics = ref({
    cpu_percent: 0,
    memory_percent: 0,
    memory_used_gb: 0,
    disk_percent: 0,
    disk_used_gb: 0,
    gpus: [],
  })

  async function fetchSystemInfo() {
    try {
      const response = await axios.get(getCompressoApiUrl('v2', 'system/status'))
      systemInfo.value = response.data
      // Seed live metrics from the initial API response
      liveMetrics.value = {
        cpu_percent: response.data.cpu?.percent || 0,
        memory_percent: response.data.memory?.percent || 0,
        memory_used_gb: response.data.memory?.used_gb || 0,
        disk_percent: response.data.disk?.percent || 0,
        disk_used_gb: response.data.disk?.used_gb || 0,
        gpus: response.data.gpus || [],
      }
    } catch (e) {
      console.error('Failed to fetch system status:', e)
    }
  }

  function startLiveMetrics(ws) {
    if (ws) {
      ws.send(JSON.stringify({ command: 'start_system_status', params: {} }))
    }
  }

  function stopLiveMetrics(ws) {
    if (ws) {
      ws.send(JSON.stringify({ command: 'stop_system_status', params: {} }))
    }
  }

  function updateLiveMetrics(data) {
    liveMetrics.value = {
      cpu_percent: data.cpu_percent ?? liveMetrics.value.cpu_percent,
      memory_percent: data.memory_percent ?? liveMetrics.value.memory_percent,
      memory_used_gb: data.memory_used_gb ?? liveMetrics.value.memory_used_gb,
      disk_percent: data.disk_percent ?? liveMetrics.value.disk_percent,
      disk_used_gb: data.disk_used_gb ?? liveMetrics.value.disk_used_gb,
      gpus: data.gpus ?? liveMetrics.value.gpus,
    }
  }

  return {
    systemInfo,
    liveMetrics,
    fetchSystemInfo,
    startLiveMetrics,
    stopLiveMetrics,
    updateLiveMetrics,
  }
}
