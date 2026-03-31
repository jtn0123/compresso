<template>
  <q-layout view="hHh lpR fff">
    <q-header class="header-background text-white">
      <q-toolbar style="min-height: 38px; height: 38px">
        <!-- Mobile menu toggle -->
        <q-btn
          v-if="$q.screen.lt.md"
          dense
          flat
          round
          :icon="leftDrawerOpen ? 'menu_open' : 'menu'"
          size="sm"
          @click="toggleDrawer"
        />

        <!-- Logo (always visible, clickable to dashboard) -->
        <q-btn flat round dense size="sm" @click="$router.push('/ui/dashboard')" class="q-mr-xs">
          <q-avatar rounded size="22px">
            <img src="~assets/compresso-logo-white.png" />
          </q-avatar>
        </q-btn>

        <div class="gt-xs">
          <SharedLinkDropdown />
        </div>

        <q-space />

        <!-- Right-side controls -->
        <div class="row items-center no-wrap q-gutter-xs">
          <PaletteSwitch class="gt-xs" />
          <ThemeSwitch class="gt-xs" />
          <q-btn dense flat round icon="notifications" size="sm" @click="toggleNotificationsDrawer">
            <q-badge
              v-if="notificationsCount > 0"
              color="red"
              text-color="white"
              floating
              style="font-size: 0.6rem; padding: 2px 4px"
            >
              {{ notificationsCount }}
            </q-badge>
            <q-tooltip>Notifications</q-tooltip>
          </q-btn>
        </div>
      </q-toolbar>
    </q-header>

    <!-- Sidebar -->
    <q-drawer
      v-model="leftDrawerOpen"
      side="left"
      :mini="!sidebarPinned && !sidebarHovered && !isMobile"
      :mini-width="56"
      :width="240"
      :behavior="isMobile ? 'mobile' : 'desktop'"
      bordered
      @mouseover="onDrawerMouseOver"
      @mouseout="onDrawerMouseOut"
      class="bg-surface-1"
    >
      <DrawerMainNav :mini="isDrawerMini" :pinned="sidebarPinned" @update:pinned="onPinToggle" />
    </q-drawer>

    <!-- Notifications drawer -->
    <q-drawer
      v-model="rightNotificationsDrawerOpen"
      side="right"
      :width="$q.screen.lt.md ? $q.screen.width : 650"
      overlay
      bordered
      :behavior="isMobile ? 'mobile' : 'desktop'"
    >
      <DrawerNotifications />
    </q-drawer>

    <q-page-container>
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </q-page-container>

    <!-- Keyboard shortcuts help dialog -->
    <KeyboardShortcutsDialog v-model="showShortcutsHelp" />

    <!-- First-run onboarding wizard -->
    <FirstRunWizard v-model="showOnboarding" />
  </q-layout>
</template>

<script>
import { onMounted, ref, computed, watch } from 'vue'
import axios from 'axios'
import { LocalStorage, useQuasar } from 'quasar'
import DrawerMainNav from 'components/drawers/DrawerMainNav'
import ThemeSwitch from 'components/ThemeSwitch'
import PaletteSwitch from 'components/PaletteSwitch'
import DrawerNotifications from 'components/drawers/DrawerNotifications'
import SharedLinkDropdown from 'components/SharedLinkDropdown'
import KeyboardShortcutsDialog from 'components/ui/KeyboardShortcutsDialog'
import FirstRunWizard from 'components/ui/FirstRunWizard'
import compressoGlobals, { getCompressoApiUrl, notificationsCount } from 'src/js/compressoGlobals'
import { useKeyboardShortcuts } from 'src/composables/useKeyboardShortcuts'
import { createLogger } from 'src/composables/useLogger'

export default {
  components: {
    DrawerMainNav,
    DrawerNotifications,
    ThemeSwitch,
    PaletteSwitch,
    SharedLinkDropdown,
    KeyboardShortcutsDialog,
    FirstRunWizard,
  },
  setup() {
    const $q = useQuasar()
    const log = createLogger('MainLayout')

    // Sidebar state
    const leftDrawerOpen = ref(!$q.screen.lt.md)
    const sidebarPinned = ref(LocalStorage.getItem('sidebar_pinned') === true)
    const sidebarHovered = ref(false)
    const rightNotificationsDrawerOpen = ref(false)

    const isMobile = computed(() => $q.screen.lt.md)
    const isDrawerMini = computed(() => !sidebarPinned.value && !sidebarHovered.value && !isMobile.value)

    function toggleDrawer() {
      leftDrawerOpen.value = !leftDrawerOpen.value
    }

    function toggleNotificationsDrawer() {
      rightNotificationsDrawerOpen.value = !rightNotificationsDrawerOpen.value
    }

    function onDrawerMouseOver() {
      if (!isMobile.value) sidebarHovered.value = true
    }

    function onDrawerMouseOut() {
      if (!isMobile.value) sidebarHovered.value = false
    }

    function onPinToggle(val) {
      sidebarPinned.value = val
      LocalStorage.set('sidebar_pinned', val)
    }

    // Keyboard shortcuts
    const { showHelp } = useKeyboardShortcuts()
    const showShortcutsHelp = ref(false)
    watch(showHelp, (val) => {
      showShortcutsHelp.value = val
    })
    watch(showShortcutsHelp, (val) => {
      showHelp.value = val
    })

    // Onboarding wizard
    const showOnboarding = ref(false)

    onMounted(() => {
      // Fetch version (used by sidebar)
      compressoGlobals.getCompressoVersion()

      // Check onboarding status
      axios
        .get(getCompressoApiUrl('v2', 'settings/read'))
        .then((res) => {
          if (!res.data?.settings?.onboarding_completed) {
            showOnboarding.value = true
          }
        })
        .catch((err) => {
          log.warn('Failed to fetch settings for onboarding check: ' + err)
        })
    })

    return {
      leftDrawerOpen,
      sidebarPinned,
      sidebarHovered,
      rightNotificationsDrawerOpen,
      isMobile,
      isDrawerMini,
      toggleDrawer,
      toggleNotificationsDrawer,
      onDrawerMouseOver,
      onDrawerMouseOut,
      onPinToggle,
      notificationsCount,
      showShortcutsHelp,
      showOnboarding,
    }
  },
}
</script>

<style scoped>
.q-toolbar {
  padding: 0 8px;
}
</style>
