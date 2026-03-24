<template>
  <q-layout view="hHh lpR lFf">

    <q-header
      reveal
      class="header-background text-white"
      height-hint="98"
      :style="leftMainNavDrawerOpen ? 'z-index: 3001' : ''"
    >
      <q-toolbar>

        <!--SHOW DRAWER MENU BUTTON-->
        <q-btn
          v-if="$route.meta.showMainNavDrawer"
          dense
          flat
          round
          :icon="leftMainNavDrawerOpen ? 'menu_open' : 'menu'"
          @click="toggleMainNavDrawer"/>

        <!--SHOW HOME BUTTON-->
        <q-btn
          v-if="$route.meta.showHome"
          dense
          flat
          round
          @click="$router.push('/ui/dashboard'); leftMainNavDrawerOpen = false"
          icon="home">
        </q-btn>

        <q-toolbar-title shrink class="row items-center no-wrap">
          <q-avatar rounded size="2rem" font-size="82px" class="q-mr-sm">
            <img src="~assets/compresso-logo-white.png">
          </q-avatar>
          <span class="brand-wordmark gt-xs">Compresso</span>
        </q-toolbar-title>

        <div class="gt-xs">
          <SharedLinkDropdown/>
        </div>

        <q-space/>

        <div class="gt-xs">
          <ThemeSwitch/>
        </div>

        <div
          class="q-gutter-sm row items-center no-wrap">
          <q-btn
            dense
            flat
            round
            icon="notifications"
            @click="toggleNotificationsDrawer">
            <q-badge
              v-if="notificationsCount > 0"
              color="red" text-color="white" floating>
              {{ notificationsCount }}
            </q-badge>
            <q-tooltip>Notifications</q-tooltip>
          </q-btn>
        </div>
      </q-toolbar>

    </q-header>

    <q-drawer
      v-if="$route.meta.showMainNavDrawer"
      v-model="leftMainNavDrawerOpen"
      side="left"
      :behavior="$q.screen.lt.md ? 'mobile' : 'desktop'">
      <DrawerMainNav/>
    </q-drawer>

    <q-drawer
      v-model="rightNotificationsDrawerOpen"
      side="right"
      :width="$q.screen.lt.md ? $q.screen.width : 650"
      :overlay="$route.meta.showMainNavDrawer"
      bordered
      :behavior="$q.screen.lt.md ? 'mobile' : 'desktop'">
      <DrawerNotifications/>
    </q-drawer>

    <q-page-container>
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </q-page-container>

    <q-footer
      class="footer-background text-white gt-sm">
      <q-toolbar style="min-height: 32px">
        <q-space />
        <span class="text-caption" style="opacity: 0.7">v{{ compressoVersion }}</span>
        <q-space />
      </q-toolbar>
    </q-footer>

  </q-layout>
</template>

<script>
import { onMounted, ref } from 'vue';
import DrawerMainNav from "components/drawers/DrawerMainNav";
import { useQuasar } from "quasar";
import ThemeSwitch from "components/ThemeSwitch";
import DrawerNotifications from "components/drawers/DrawerNotifications";
import SharedLinkDropdown from "components/SharedLinkDropdown";
import compressoGlobals, { notificationsCount } from "src/js/compressoGlobals";

export default {
  components: {
    DrawerMainNav,
    DrawerNotifications,
    ThemeSwitch,
    SharedLinkDropdown
  },
  setup() {
    const $q = useQuasar();

    const leftMainNavDrawerOpen = ref(false)
    const rightNotificationsDrawerOpen = ref(false)

    const compressoVersion = ref('')

    function toggleMainNavDrawer() {
      leftMainNavDrawerOpen.value = !leftMainNavDrawerOpen.value
    }

    function toggleNotificationsDrawer() {
      rightNotificationsDrawerOpen.value = !rightNotificationsDrawerOpen.value
    }

    onMounted(() => {
      // Fetch version
      compressoGlobals.getCompressoVersion().then((version) => {
        compressoVersion.value = version;
      })
    })

    return {
      leftMainNavDrawerOpen,
      rightNotificationsDrawerOpen,
      toggleMainNavDrawer,
      toggleNotificationsDrawer,

      notificationsCount,
      compressoVersion
    }
  }
}
</script>

<style scoped>
.brand-wordmark {
  font-size: 1.15rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.92;
}
</style>
