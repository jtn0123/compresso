<template>
  <div class="library-donut-chart">
    <div v-if="loading" class="text-center q-pa-md">
      <q-spinner-dots size="40px" color="primary" />
    </div>
    <template v-else>
      <div class="donut-wrapper">
        <canvas ref="chartRef" aria-label="Library optimization progress chart"></canvas>
        <div class="donut-center-overlay">
          <div class="text-h3 text-weight-bold text-primary">{{ percent }}%</div>
          <div class="text-caption text-grey">{{ $t('flow.optimizationProgress') }}</div>
        </div>
      </div>
      <div class="text-caption text-center text-grey q-mt-sm">
        {{ processedFiles.toLocaleString() }} {{ $t('dashboard.ofTotal') }} {{ totalFiles.toLocaleString() }}
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'

const $q = useQuasar()
const { t: $t } = useI18n()

const props = defineProps({
  totalFiles: { type: Number, default: 0 },
  processedFiles: { type: Number, default: 0 },
  percent: { type: Number, default: 0 },
  loading: { type: Boolean, default: false }
})

const chartRef = ref(null)
let chart = null

async function renderChart() {
  const { Chart, DoughnutController, ArcElement, Tooltip } = await import('chart.js')
  Chart.register(DoughnutController, ArcElement, Tooltip)

  await nextTick()

  if (chart) chart.destroy()
  if (!chartRef.value) return

  const isDark = $q.dark.isActive
  const remainingColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'
  const processed = props.processedFiles || 0
  const remaining = Math.max(0, (props.totalFiles || 0) - processed)

  chart = new Chart(chartRef.value, {
    type: 'doughnut',
    data: {
      labels: [$t('flow.optimizationProgress'), $t('dashboard.remaining')],
      datasets: [{
        data: [processed, remaining],
        backgroundColor: ['#1a6b4a', remainingColor],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '75%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.raw.toLocaleString()}`
          }
        }
      }
    }
  })
}

watch(() => [props.totalFiles, props.processedFiles, props.loading, $q.dark.isActive], () => {
  if (!props.loading) renderChart()
}, { deep: true })

onMounted(() => {
  if (!props.loading) renderChart()
})

onBeforeUnmount(() => {
  if (chart) { chart.destroy(); chart = null }
})
</script>

<style scoped>
.donut-wrapper {
  position: relative;
  max-width: 220px;
  margin: 0 auto;
}
.donut-center-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
}
</style>
