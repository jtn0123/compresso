<template>
  <div class="drawer-profile">
    <q-img src="~assets/bg-design-3.png" style="height: 90px">
      <div class="absolute-full profile-gradient"></div>

      <!-- USER PROFILE -->
      <div class="absolute-top bg-transparent q-pa-md row items-start">
        <q-avatar v-if="compressoSession" rounded size="56px" class="q-mr-sm">
          <q-img :src="compressoSession.picture_uri || '/compresso/img/avatar_placeholder.png'" />
        </q-avatar>
        <div v-if="compressoSession && compressoSession.name" class="text-weight-bold q-pt-xs">
          {{ compressoSession.name }}
        </div>
      </div>
    </q-img>
  </div>
</template>

<script>
import { ref } from 'vue'
import compressoGlobals from 'src/js/compressoGlobals'

export default {
  name: 'DrawerUserProfileHeader',
  setup() {
    const compressoSession = ref(null)

    compressoGlobals.getCompressoSession().then((session) => {
      compressoSession.value = session
    })

    return {
      compressoSession,
    }
  },
}
</script>

<style>
.profile-gradient {
  background: linear-gradient(
    to bottom,
    var(--compresso-header-bg),
    color-mix(in srgb, var(--compresso-header-bg), transparent 30%)
  ) !important;
}
</style>
