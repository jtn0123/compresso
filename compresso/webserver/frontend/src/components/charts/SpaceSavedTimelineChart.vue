<template>
  <q-card>
    <q-card-section>
      <div class="row items-center">
        <div class="text-h6 col">Space Saved Over Time</div>
        <q-btn-toggle
          v-model="interval"
          toggle-color="primary"
          :options="[
            { label: 'Day', value: 'day' },
            { label: 'Week', value: 'week' },
            { label: 'Month', value: 'month' },
          ]"
          dense
          flat
          @update:model-value="$emit('interval-change', interval)"
        />
      </div>
    </q-card-section>
    <q-card-section v-if="loading" class="text-center">
      <q-spinner-dots size="40px" color="primary" />
    </q-card-section>
    <q-card-section v-else>
      <canvas ref="chartRef" aria-label="Space saved over time chart"></canvas>
    </q-card-section>
  </q-card>
</template>

<script>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useQuasar } from 'quasar'
import { formatBytes } from 'src/js/formatUtils'
import { useChartTheme } from 'src/composables/useChartTheme'

export default {
  name: 'SpaceSavedTimelineChart',
  props: {
    data: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  emits: ['interval-change'],
  setup(props) {
    const $q = useQuasar()
    const { getChartColor, chartBgColor } = useChartTheme()
    const chartRef = ref(null)
    const interval = ref('day')
    let chart = null

    async function renderChart() {
      const { Chart, LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } =
        await import('chart.js')
      Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

      await nextTick()

      if (chart) chart.destroy()

      if (chartRef.value && props.data.length > 0) {
        const isDark = $q.dark.isActive
        const gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'
        const labelColor = isDark ? '#ccc' : '#666'
        const titleColor = isDark ? '#eee' : '#333'

        chart = new Chart(chartRef.value, {
          type: 'line',
          data: {
            labels: props.data.map((d) => d.date),
            datasets: [
              {
                label: 'Space Saved',
                data: props.data.map((d) => d.space_saved),
                borderColor: getChartColor(1),
                backgroundColor: chartBgColor(1, 0.1),
                fill: true,
                tension: 0.3,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              tooltip: {
                callbacks: {
                  label: (ctx) => 'Saved: ' + formatBytes(ctx.parsed.y),
                },
              },
              legend: {
                labels: { color: labelColor },
              },
            },
            scales: {
              x: {
                ticks: { color: labelColor },
                grid: { color: gridColor },
              },
              y: {
                beginAtZero: true,
                ticks: {
                  callback: (val) => formatBytes(val),
                  color: labelColor,
                },
                title: { display: false, color: titleColor },
                grid: { color: gridColor },
              },
            },
          },
        })
      }
    }

    watch(
      () => props.data,
      () => {
        if (!props.loading) renderChart()
      },
      { deep: true },
    )
    watch(() => $q.dark.isActive, renderChart)

    onMounted(() => {
      if (!props.loading) renderChart()
    })

    onBeforeUnmount(() => {
      if (chart) {
        chart.destroy()
        chart = null
      }
    })

    return { chartRef, interval }
  },
}
</script>
