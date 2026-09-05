<template>
  <q-page class="flex flex-center">
    <q-spinner color="primary" size="3em" />
  </q-page>
</template>

<script lang="ts">
import { onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { createLogger } from 'src/composables/useLogger'

export default {
  setup() {
    const router = useRouter()
    const route = useRoute()
    const log = createLogger('ActionTrigger')

    function navigateToDashboard() {
      router.replace('/ui/dashboard')
    }

    function reloadSession() {
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'session/reload'),
      })
        .catch(() => {
          log.error('Failed to reload session.')
        })
        .finally(() => {
          // Always leave this action-only route; never strand the user
          // on a blank page, whether the reload succeeded or failed.
          navigateToDashboard()
        })
    }

    onMounted(() => {
      if (route.query?.session === 'reload') {
        reloadSession()
      } else {
        // No recognized action — this route renders no content of its
        // own, so redirect instead of showing a blank page.
        navigateToDashboard()
      }
    })

    return {}
  },
}
</script>
