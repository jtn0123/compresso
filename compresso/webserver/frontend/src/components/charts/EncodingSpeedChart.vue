<template>
  <q-card>
    <q-card-section>
      <div class="text-h6">{{ $t('pages.compressionDashboard.encodingSpeed') }}</div>
      <div class="text-caption text-grey">{{ $t('pages.compressionDashboard.encodingSpeedCaption') }}</div>
    </q-card-section>
    <q-card-section v-if="loading" class="text-center">
      <q-spinner-dots size="40px" color="primary" />
    </q-card-section>
    <q-card-section v-else-if="data.length === 0" class="text-center text-grey">
      {{ $t('pages.compressionDashboard.noSpeedData') }}
    </q-card-section>
    <q-card-section v-else>
      <canvas ref="chartRef" aria-label="Encoding speed chart" style="max-height: 280px"></canvas>
    </q-card-section>
  </q-card>
</template>

<script>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { useQuasar } from 'quasar';
import { useChartTheme } from 'src/composables/useChartTheme';

export default {
  name: 'EncodingSpeedChart',
  props: {
    data: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  setup(props) {
    const { t } = useI18n();
    const $q = useQuasar();
    const { getChartColor, chartBgColor } = useChartTheme();
    const chartRef = ref(null);
    let chart = null;

    async function renderChart() {
      const { Chart, LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, BarController, BarElement } = await import('chart.js');
      Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, BarController, BarElement);

      await nextTick();

      if (chart) chart.destroy();

      if (chartRef.value && props.data.length > 0) {
        const isDark = $q.dark.isActive;
        const gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
        const labelColor = isDark ? '#ccc' : '#666';
        const titleColor = isDark ? '#eee' : '#333';

        // Group by date, averaging across codecs
        const dateMap = {};
        for (const d of props.data) {
          if (!dateMap[d.date]) {
            dateMap[d.date] = { fps_sum: 0, speed_sum: 0, count: 0 };
          }
          dateMap[d.date].fps_sum += d.avg_fps * d.count;
          dateMap[d.date].speed_sum += d.avg_speed_ratio * d.count;
          dateMap[d.date].count += d.count;
        }

        const dates = Object.keys(dateMap).sort();
        const fpsData = dates.map(d => dateMap[d].count > 0 ? dateMap[d].fps_sum / dateMap[d].count : 0);
        const speedData = dates.map(d => dateMap[d].count > 0 ? dateMap[d].speed_sum / dateMap[d].count : 0);

        chart = new Chart(chartRef.value, {
          type: 'line',
          data: {
            labels: dates,
            datasets: [
              {
                label: t('pages.compressionDashboard.avgFps'),
                data: fpsData,
                borderColor: getChartColor(1),
                backgroundColor: chartBgColor(1, 0.1),
                yAxisID: 'y',
                tension: 0.3,
              },
              {
                label: t('pages.compressionDashboard.speedRatio'),
                data: speedData,
                borderColor: getChartColor(2),
                backgroundColor: chartBgColor(2, 0.1),
                yAxisID: 'y1',
                tension: 0.3,
              },
            ],
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
                    if (ctx.datasetIndex === 0) return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + ' fps';
                    return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(2) + 'x';
                  },
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
                type: 'linear',
                position: 'left',
                beginAtZero: true,
                title: { display: true, text: t('pages.compressionDashboard.fpsAxisTitle'), color: titleColor },
                ticks: { color: labelColor },
                grid: { color: gridColor },
              },
              y1: {
                type: 'linear',
                position: 'right',
                beginAtZero: true,
                title: { display: true, text: t('pages.compressionDashboard.speedAxisTitle'), color: titleColor },
                ticks: { color: labelColor },
                grid: { drawOnChartArea: false },
              },
            },
          },
        });
      }
    }

    watch(() => props.data, renderChart, { deep: true });
    watch(() => props.loading, (val) => {
      if (!val) renderChart();
    });
    watch(() => $q.dark.isActive, renderChart);

    onMounted(() => {
      if (!props.loading && props.data.length > 0) renderChart();
    });

    onBeforeUnmount(() => {
      if (chart) chart.destroy();
    });

    return { chartRef };
  },
};
</script>
