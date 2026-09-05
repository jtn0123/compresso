<template>
  <div class="column fit">
    <div :class="{ 'q-mt-xl': !$q.screen.gt.sm }"></div>
    <q-scroll-area class="col">
      <q-list padding>
        <q-item-label header>{{ $t('navigation.dataPanels') }}:</q-item-label>

        <q-item
          v-for="(item, index) in availableDataPanels"
          :key="index"
          clickable
          @click="$router.push('/ui/data-panels?pluginId=' + item.id)"
          v-ripple
        >
          <q-item-section avatar>
            <q-icon name="insights" />
          </q-item-section>
          <q-item-section>
            {{ item.label }}
          </q-item-section>
        </q-item>
      </q-list>
    </q-scroll-area>
  </div>
</template>

<script lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import type { ApiSchema } from 'src/types/contracts'

interface DataPanelLink {
  id: string
  label: string
}

export default {
  name: 'DrawerDataPanelsNav',
  methods: {
    setPage(value: string) {
      this.$router.push('/ui/data-panels?pluginId=' + value)
    },
    fetchDataPanelList() {
      axios<ApiSchema<'PluginsDataPanelTypesData'>>({
        method: 'get',
        url: getCompressoApiUrl('v2', 'plugins/panels/enabled'),
      })
        .then((response) => {
          // Success
          const pluginIds: DataPanelLink[] = []
          for (let i = 0; i < response.data.results.length; i++) {
            const plugin = response.data.results[i]
            if (!plugin) continue
            pluginIds.push({
              id: plugin.plugin_id,
              label: plugin.name,
            })
          }
          this.availableDataPanels = pluginIds
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('notifications.failedToFetchEnabledDataPanelPlugins'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
  },
  created() {
    this.fetchDataPanelList()
  },
  data: function () {
    const availableDataPanels = ref<DataPanelLink[]>([])
    return {
      availableDataPanels,
    }
  },
}
</script>
