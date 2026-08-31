<template>
  <q-page>
    <div class="iframe-container">
      <iframe v-if="iframeSrc !== null" id="data-panel-iframe" :src="iframeSrc" title="Plugin data panel">
        Your browser is not supported. Sorry.
      </iframe>

      <div v-else>
        <div class="full-width column flex-center q-mt-xl q-pt-xl">
          <q-icon size="64px" name="extension" class="text-secondary" />
          <q-item-label class="text-subtitle1 text-secondary q-mt-md">
            {{ $t('components.dataPanels.noDataPanelsEnabled') }}
          </q-item-label>
          <div class="text-caption text-secondary q-mt-sm data-panels-empty-caption">
            {{ $t('pages.dataPanels.bannerText') }}
          </div>
        </div>
      </div>
    </div>
  </q-page>
</template>

<script lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { LocalStorage } from 'quasar'
import type { ApiSchema } from 'src/types/contracts'

export default {
  data() {
    const iframeSrc = ref<string | null>(null)
    return {
      page: '',
      iframeSrc,
      iframeHeight: '0px',
    }
  },
  created() {
    //window.addEventListener('message', this.resizeIframe);
    if (typeof this.$route.query !== 'undefined' && typeof this.$route.query.pluginId !== 'undefined') {
      this.setPageFromParams(this.$route.query.pluginId)
    } else {
      this.setPageAsFirstEnabledPanel()
    }
  },
  methods: {
    setPageFromParams(pluginId: unknown) {
      const normalizedPluginId = Array.isArray(pluginId) ? pluginId[0] : pluginId
      if (typeof normalizedPluginId === 'string') {
        let theme = LocalStorage.getItem('theme')
        this.iframeSrc = '/compresso/panel/' + normalizedPluginId + '/?theme=' + theme
      }
    },
    setPageAsFirstEnabledPanel() {
      axios<ApiSchema<'PluginsDataPanelTypesData'>>({
        method: 'get',
        url: getCompressoApiUrl('v2', 'plugins/panels/enabled'),
      })
        .then((response) => {
          // Success
          if (response.data.results.length > 0) {
            const first = response.data.results[0]
            if (first) this.setPageFromParams(first.plugin_id)
          }
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
  watch: {
    $route(to, _from) {
      if (typeof to.query !== 'undefined') {
        this.setPageFromParams(to.query.pluginId)
      }
    },
  },
}
</script>

<style scoped>
.data-panels-empty-caption {
  max-width: 400px;
  text-align: center;
}

.iframe-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  margin: 20px;
}

.iframe-container iframe {
  display: block;
  width: 100%;
  height: 100%;
  border: none;
}
</style>
