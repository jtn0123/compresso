<template>
  <div class="drawer-profile">
    <q-img
      src="~assets/bg-design-3.png"
      style="height: 90px">
      <div class="absolute-full profile-gradient"></div>

      <!-- USER PROFILE -->
      <div class="absolute-top bg-transparent q-pa-md row items-start">
        <q-avatar
          v-if="unmanicSession"
          rounded
          size="56px"
          class="q-mr-sm">
          <q-img :src="unmanicSession.picture_uri || '/unmanic/img/avatar_placeholder.png'"/>
        </q-avatar>
        <div
          v-if="unmanicSession && unmanicSession.name"
          class="text-weight-bold q-pt-xs">
          {{ unmanicSession.name }}
        </div>
      </div>
    </q-img>
  </div>
</template>

<script>

import { ref } from "vue";
import unmanicGlobals from "src/js/unmanicGlobals";

export default {
  name: 'DrawerUserProfileHeader',
  setup() {
    const unmanicSession = ref(null);

    unmanicGlobals.getUnmanicSession().then((session) => {
      unmanicSession.value = session;
    })

    return {
      unmanicSession,
    }
  }
}
</script>

<style>
.profile-gradient {
  background: linear-gradient(to bottom, #002e5c, rgba(0, 46, 92, 0.7)) !important;
}
</style>
