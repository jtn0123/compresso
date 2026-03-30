<template>
  <q-card>
    <q-card-section>
      <div class="text-h6">Codec Distribution</div>
    </q-card-section>
    <q-card-section v-if="loading" class="text-center">
      <q-spinner-dots size="40px" color="primary" />
    </q-card-section>
    <q-card-section v-else>
      <div class="row q-col-gutter-md">
        <div class="col-12 col-md-6">
          <div class="text-subtitle2 text-center q-mb-sm">Source Codecs</div>
          <canvas ref="sourceChartRef" aria-label="Source codec distribution chart"></canvas>
        </div>
        <div class="col-12 col-md-6">
          <div class="text-subtitle2 text-center q-mb-sm">Destination Codecs</div>
          <canvas ref="destChartRef" aria-label="Destination codec distribution chart"></canvas>
        </div>
      </div>
    </q-card-section>
  </q-card>
</template>

<script>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useQuasar } from 'quasar'
import { useChartTheme } from 'src/composables/useChartTheme'

export default {
  name: 'CodecDistributionChart',
  props: {
    sourceCodecs: { type: Array, default: () => [] },
    destinationCodecs: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  setup(props) {
    const $q = useQuasar()
    const { getChartColors } = useChartTheme()
    const sourceChartRef = ref(null)
    const destChartRef = ref(null)
    let sourceChart = null
    let destChart = null

    async function renderCharts() {
      const { Chart, DoughnutController, ArcElement, Tooltip, Legend } = await import('chart.js')
      Chart.register(DoughnutController, ArcElement, Tooltip, Legend)

      await nextTick()

      if (sourceChart) sourceChart.destroy()
      if (destChart) destChart.destroy()

      const isDark = $q.dark.isActive
      const labelColor = isDark ? '#ccc' : '#666'

      if (sourceChartRef.value && props.sourceCodecs.length > 0) {
        sourceChart = new Chart(sourceChartRef.value, {
          type: 'doughnut',
          data: {
            labels: props.sourceCodecs.map((c) => c.codec),
            datasets: [
              {
                data: props.sourceCodecs.map((c) => c.count),
                backgroundColor: getChartColors().slice(0, props.sourceCodecs.length),
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'bottom',
                labels: { color: labelColor },
              },
            },
          },
        })
      }

      if (destChartRef.value && props.destinationCodecs.length > 0) {
        destChart = new Chart(destChartRef.value, {
          type: 'doughnut',
          data: {
            labels: props.destinationCodecs.map((c) => c.codec),
            datasets: [
              {
                data: props.destinationCodecs.map((c) => c.count),
                backgroundColor: getChartColors().slice(0, props.destinationCodecs.length),
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'bottom',
                labels: { color: labelColor },
              },
            },
          },
        })
      }
    }

    watch(
      () => [props.sourceCodecs, props.destinationCodecs],
      () => {
        if (!props.loading) renderCharts()
      },
      { deep: true },
    )
    watch(() => $q.dark.isActive, renderCharts)

    onMounted(() => {
      if (!props.loading) renderCharts()
    })

    onBeforeUnmount(() => {
      if (sourceChart) {
        sourceChart.destroy()
        sourceChart = null
      }
      if (destChart) {
        destChart.destroy()
        destChart = null
      }
    })

    return { sourceChartRef, destChartRef }
  },
}
</script>
