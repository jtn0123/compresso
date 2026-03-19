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
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { formatBytes } from 'src/js/formatUtils';

export default {
  name: 'SpaceSavedTimelineChart',
  props: {
    data: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  emits: ['interval-change'],
  setup(props) {
    const chartRef = ref(null);
    const interval = ref('day');
    let chart = null;

    async function renderChart() {
      const { Chart, LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } = await import('chart.js');
      Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler);

      await nextTick();

      if (chart) chart.destroy();

      if (chartRef.value && props.data.length > 0) {
        chart = new Chart(chartRef.value, {
          type: 'line',
          data: {
            labels: props.data.map(d => d.date),
            datasets: [{
              label: 'Space Saved',
              data: props.data.map(d => d.space_saved),
              borderColor: '#1a6b4a',
              backgroundColor: 'rgba(26, 107, 74, 0.1)',
              fill: true,
              tension: 0.3,
            }],
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
            },
            scales: {
              y: {
                beginAtZero: true,
                ticks: {
                  callback: (val) => formatBytes(val),
                },
              },
            },
          },
        });
      }
    }

    watch(() => props.data, () => {
      if (!props.loading) renderChart();
    }, { deep: true });

    onMounted(() => {
      if (!props.loading) renderChart();
    });

    onBeforeUnmount(() => {
      if (chart) { chart.destroy(); chart = null; }
    });

    return { chartRef, interval };
  },
};
</script>
