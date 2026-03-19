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
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';

const CHART_COLORS = [
  '#1a6b4a', '#e8a525', '#7c5cbf', '#d43545', '#2e9e5a',
  '#3a8fd4', '#e67e22', '#1abc9c', '#34495e', '#95a5a6',
];

export default {
  name: 'CodecDistributionChart',
  props: {
    sourceCodecs: { type: Array, default: () => [] },
    destinationCodecs: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  setup(props) {
    const sourceChartRef = ref(null);
    const destChartRef = ref(null);
    let sourceChart = null;
    let destChart = null;

    async function renderCharts() {
      const { Chart, DoughnutController, ArcElement, Tooltip, Legend } = await import('chart.js');
      Chart.register(DoughnutController, ArcElement, Tooltip, Legend);

      await nextTick();

      if (sourceChart) sourceChart.destroy();
      if (destChart) destChart.destroy();

      if (sourceChartRef.value && props.sourceCodecs.length > 0) {
        sourceChart = new Chart(sourceChartRef.value, {
          type: 'doughnut',
          data: {
            labels: props.sourceCodecs.map(c => c.codec),
            datasets: [{
              data: props.sourceCodecs.map(c => c.count),
              backgroundColor: CHART_COLORS.slice(0, props.sourceCodecs.length),
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
          },
        });
      }

      if (destChartRef.value && props.destinationCodecs.length > 0) {
        destChart = new Chart(destChartRef.value, {
          type: 'doughnut',
          data: {
            labels: props.destinationCodecs.map(c => c.codec),
            datasets: [{
              data: props.destinationCodecs.map(c => c.count),
              backgroundColor: CHART_COLORS.slice(0, props.destinationCodecs.length),
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
          },
        });
      }
    }

    watch(() => [props.sourceCodecs, props.destinationCodecs], () => {
      if (!props.loading) renderCharts();
    }, { deep: true });

    onMounted(() => {
      if (!props.loading) renderCharts();
    });

    onBeforeUnmount(() => {
      if (sourceChart) { sourceChart.destroy(); sourceChart = null; }
      if (destChart) { destChart.destroy(); destChart = null; }
    });

    return { sourceChartRef, destChartRef };
  },
};
</script>
