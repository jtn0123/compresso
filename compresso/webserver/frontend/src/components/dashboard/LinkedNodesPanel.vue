<template>
  <q-card flat bordered>
    <q-expansion-item
      :label="$t('linkedNodes.title')"
      :caption="lastUpdated ? $t('common.updatedAgo', { time: relativeTime }) : ''"
      icon="device_hub"
      header-class="bg-card-head text-primary"
      :default-opened="false"
    >
      <q-list separator>
        <template v-if="remoteInstallations.length > 0">
          <q-item v-for="node in remoteInstallations" :key="node.uuid">
            <q-item-section avatar>
              <q-icon
                :name="node.available ? 'circle' : 'circle'"
                :color="node.available ? 'positive' : 'negative'"
                size="12px"
              />
            </q-item-section>

            <q-item-section>
              <q-item-label>{{ node.name || node.address }}</q-item-label>
              <q-item-label caption>
                <span v-if="node.version">v{{ node.version }}</span>
                <span v-if="!node.available" class="text-negative q-ml-sm">{{ $t('linkedNodes.offline') }}</span>
              </q-item-label>
            </q-item-section>

            <q-item-section side>
              <div class="row q-gutter-xs">
                <q-badge v-if="node.enable_receiving_tasks" color="blue-3" text-color="dark">
                  ← {{ $t('linkedNodes.receiving') }}
                </q-badge>
                <q-badge v-if="node.enable_sending_tasks" color="green-3" text-color="dark">
                  → {{ $t('linkedNodes.sending') }}
                </q-badge>
              </div>
            </q-item-section>
          </q-item>
        </template>
        <q-item v-else>
          <q-item-section>
            <q-item-label class="text-grey text-caption">
              <q-icon v-if="fetchError" name="warning" color="negative" class="q-mr-xs" />
              {{ fetchError ? $t('linkedNodes.fetchError') : $t('linkedNodes.noNodes') }}
            </q-item-label>
          </q-item-section>
        </q-item>

        <q-item clickable @click="$router.push('/ui/settings-link')">
          <q-item-section>
            <q-item-label class="text-primary">{{ $t('linkedNodes.configure') }} →</q-item-label>
          </q-item-section>
        </q-item>
      </q-list>
    </q-expansion-item>
  </q-card>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { useRelativeTime } from 'src/composables/useRelativeTime'

const { t: $t } = useI18n()
const lastUpdated = ref(null)
const { relativeTime } = useRelativeTime(lastUpdated)
const remoteInstallations = ref([])
const fetchError = ref(false)
let pollInterval = null

async function fetchRemoteInstallations() {
  try {
    const response = await axios.get(getCompressoApiUrl('v2', 'settings/read'))
    remoteInstallations.value = response.data.settings?.remote_installations || []
    fetchError.value = false
    lastUpdated.value = Date.now()
  } catch (_e) {
    fetchError.value = true
  }
}

onMounted(() => {
  fetchRemoteInstallations()
  pollInterval = setInterval(fetchRemoteInstallations, 60000)
})

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval)
  }
})
</script>
