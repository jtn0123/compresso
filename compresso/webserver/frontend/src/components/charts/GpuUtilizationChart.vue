<template>
  <q-card flat bordered>
    <q-card-section>
      <div class="text-h6">{{ $t('gpu.chartTitle') }}</div>
      <div class="text-caption gpu-chart-caption">{{ $t('gpu.chartCaption') }}</div>
    </q-card-section>
    <q-card-section v-if="!hasData" class="text-center gpu-chart-caption">
      {{ $t('gpu.noData') }}
    </q-card-section>
    <q-card-section v-else>
      <canvas ref="chartRef" :aria-label="$t('gpu.chartAriaLabel')" class="gpu-chart-canvas"></canvas>
    </q-card-section>
  </q-card>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useChartTheme } from 'src/composables/useChartTheme';

const { getChartColor, chartBgColor } = useChartTheme();

const GPU_COLORS = {
  nvidia: { border: '#76b900', bg: 'rgba(118, 185, 0, 0.1)' },
  intel: { border: '#3498db', bg: 'rgba(52, 152, 219, 0.1)' },
  amd: { border: '#e74c3c', bg: 'rgba(231, 76, 60, 0.1)' },
};

const TEMP_COLORS = {
  nvidia: '#2ecc71',
  intel: '#85c1e9',
  amd: '#f1948a',
};

function getGpuColor(type) {
  return GPU_COLORS[type] || { border: getChartColor(3), bg: chartBgColor(3, 0.1) };
}

function getTempColor(type) {
  return TEMP_COLORS[type] || getChartColor(4);
}

function gpuTypeColor(gpuName) {
  const lower = (gpuName || '').toLowerCase();
  if (lower.includes('nvidia') || lower.includes('geforce') || lower.includes('rtx') || lower.includes('gtx')) return 'nvidia';
  if (lower.includes('intel') || lower.includes('arc') || lower.includes('iris') || lower.includes('uhd')) return 'intel';
  if (lower.includes('amd') || lower.includes('radeon') || lower.includes('rx ')) return 'amd';
  return 'default';
}

const props = defineProps({
  gpuHistory: { type: Object, default: () => ({}) },
});

const { t } = useI18n();
const $q = useQuasar();
const chartRef = ref(null);
let chart = null;

const hasData = computed(() => {
  if (!props.gpuHistory || typeof props.gpuHistory !== 'object') return false;
  return Object.values(props.gpuHistory).some(arr => Array.isArray(arr) && arr.length > 0);
});

function formatTime(timestamp) {
  const d = new Date(timestamp * 1000);
  return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
}

async function renderChart() {
  const { Chart, LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend } = await import('chart.js');
  Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend);

  await nextTick();

  if (chart) chart.destroy();

  if (!chartRef.value || !hasData.value) return;

  const isDark = $q.dark.isActive;
  const gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
  const labelColor = isDark ? '#aaa' : '#666';

  const datasets = [];
  let allLabels = [];

  for (const [gpuIndex, points] of Object.entries(props.gpuHistory)) {
    if (!Array.isArray(points) || points.length === 0) continue;

    const gpuName = points[0]?.gpu_name || t('gpu.gpuFallbackLabel', { index: gpuIndex });
    const type = gpuTypeColor(gpuName);
    const colors = getGpuColor(type);
    const tempColor = getTempColor(type);

    const labels = points.map(p => formatTime(p.timestamp));
    if (labels.length > allLabels.length) allLabels = labels;

    const utilizationData = points.map(p => p.utilization_percent ?? 0);
    const temperatureData = points.map(p => p.temperature_c ?? null);

    datasets.push({
      label: t('gpu.utilizationDatasetLabel', { name: gpuName }),
      data: utilizationData,
      borderColor: colors.border,
      backgroundColor: colors.bg,
      yAxisID: 'y',
      tension: 0.3,
      pointRadius: 0,
      borderWidth: 2,
    });

    const hasTemp = temperatureData.some(v => v !== null && v > 0);
    if (hasTemp) {
      datasets.push({
        label: t('gpu.temperatureDatasetLabel', { name: gpuName }),
        data: temperatureData,
        borderColor: tempColor,
        backgroundColor: 'transparent',
        yAxisID: 'y1',
        tension: 0.3,
        borderDash: [5, 3],
        pointRadius: 0,
        borderWidth: 1.5,
      });
    }
  }

  chart = new Chart(chartRef.value, {
    type: 'line',
    data: {
      labels: allLabels,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.yAxisID === 'y1') {
                return ctx.dataset.label + ': ' + (ctx.parsed.y != null ? ctx.parsed.y.toFixed(0) + '\u00B0C' : t('gpu.notAvailable'));
              }
              return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%';
            },
          },
        },
        legend: {
          labels: {
            color: labelColor,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: labelColor, maxTicksLimit: 10 },
          grid: { color: gridColor },
        },
        y: {
          type: 'linear',
          position: 'left',
          min: 0,
          max: 100,
          title: { display: true, text: t('gpu.utilizationPercent'), color: labelColor },
          ticks: { color: labelColor },
          grid: { color: gridColor },
        },
        y1: {
          type: 'linear',
          position: 'right',
          min: 0,
          suggestedMax: 100,
          title: { display: true, text: t('gpu.temperatureAxis'), color: labelColor },
          ticks: { color: labelColor },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
}

watch(() => props.gpuHistory, renderChart, { deep: true });
watch(() => $q.dark.isActive, renderChart);

onMounted(() => {
  if (hasData.value) renderChart();
});

onBeforeUnmount(() => {
  if (chart) chart.destroy();
});

defineExpose({ hasData });
</script>

<style scoped>
.gpu-chart-caption {
  color: var(--q-grey, #9e9e9e);
}
.gpu-chart-canvas {
  max-height: 280px;
}
</style>
