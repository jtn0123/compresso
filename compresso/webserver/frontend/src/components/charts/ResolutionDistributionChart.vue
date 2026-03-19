<template>
  <q-card>
    <q-card-section>
      <div class="text-h6">Resolution Distribution</div>
    </q-card-section>
    <q-card-section v-if="loading" class="text-center">
      <q-spinner-dots size="40px" color="primary" />
    </q-card-section>
    <q-card-section v-else>
      <canvas ref="chartRef" aria-label="Resolution distribution chart"></canvas>
    </q-card-section>
  </q-card>
</template>

<script>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';

export default {
  name: 'ResolutionDistributionChart',
  props: {
    resolutions: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  setup(props) {
    const chartRef = ref(null);
    let chart = null;

    async function renderChart() {
      const { Chart, BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend } = await import('chart.js');
      Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

      await nextTick();

      if (chart) chart.destroy();

      if (chartRef.value && props.resolutions.length > 0) {
        chart = new Chart(chartRef.value, {
          type: 'bar',
          data: {
            labels: props.resolutions.map(r => r.resolution),
            datasets: [{
              label: 'Files',
              data: props.resolutions.map(r => r.count),
              backgroundColor: '#e8a525',
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              y: { beginAtZero: true, ticks: { stepSize: 1 } },
            },
          },
        });
      }
    }

    watch(() => props.resolutions, () => {
      if (!props.loading) renderChart();
    }, { deep: true });

    onMounted(() => {
      if (!props.loading) renderChart();
    });

    onBeforeUnmount(() => {
      if (chart) { chart.destroy(); chart = null; }
    });

    return { chartRef };
  },
};
</script>
