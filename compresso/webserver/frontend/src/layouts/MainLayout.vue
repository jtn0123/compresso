<template>
  <q-layout view="hHh lpR fff">
    <q-header class="app-topbar">
      <q-toolbar style="min-height: 52px; height: 52px; padding: 0 16px 0 8px">
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

        <!-- Logo (mobile only — desktop shows it in the sidebar) -->
        <q-btn v-if="$q.screen.lt.md" flat round dense size="sm" @click="$router.push('/ui/dashboard')" class="q-mr-xs">
          <q-avatar rounded size="22px">
            <img src="~assets/compresso-logo-white.png" :alt="$t('a11y.logoAlt')" />
          </q-avatar>
        </q-btn>

        <!-- Page title + subtitle -->
        <div class="col q-pl-sm" style="min-width: 0">
          <div class="topbar-title ellipsis">{{ pageTitle }}</div>
          <div class="topbar-subtitle ellipsis gt-xs">{{ pageSubtitle }}</div>
        </div>

        <!-- Right-side controls -->
        <div class="row items-center no-wrap" style="gap: 14px">
          <!-- System meters -->
          <div v-if="$q.screen.gt.sm" class="row items-center no-wrap" style="gap: 14px">
            <div v-for="meter in meters" :key="meter.label" class="row items-center no-wrap" style="gap: 6px">
              <span class="topbar-meter-label">{{ meter.label }}</span>
              <div class="topbar-meter-track">
                <div class="topbar-meter-fill" :style="{ width: meter.percent + '%', background: meter.color }"></div>
              </div>
              <span class="topbar-meter-value">{{ meter.percent }}%</span>
            </div>
            <div class="topbar-divider"></div>
          </div>

          <!-- Live connection indicator -->
          <div class="row items-center no-wrap" style="gap: 6px">
            <div
              :class="[
                'connection-dot',
                connectionState === 'connected'
                  ? 'connection-dot--connected'
                  : connectionState === 'connecting'
                    ? 'connection-dot--connecting'
                    : 'connection-dot--disconnected',
              ]"
            />
            <span class="text-caption text-weight-medium" :class="connectionTextClass" style="font-size: 11px">
              {{ connectionLabel }}
            </span>
            <q-tooltip>
              {{
                connectionState === 'connected' ? $t('systemStatus.realtimeActive') : $t('systemStatus.realtimeLost')
              }}
            </q-tooltip>
          </div>

          <div class="gt-xs">
            <SharedLinkDropdown />
          </div>
          <div class="row items-center no-wrap q-gutter-xs">
            <PaletteSwitch class="gt-xs" />
            <ThemeSwitch class="gt-xs" />
            <q-btn
              dense
              flat
              round
              icon="notifications"
              size="sm"
              :aria-label="$t('a11y.notifications')"
              @click="toggleNotificationsDrawer"
            >
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
        </div>
      </q-toolbar>
    </q-header>

    <!-- Sidebar -->
    <q-drawer
      v-model="leftDrawerOpen"
      side="left"
      :mini="!sidebarPinned && !sidebarHovered && !isMobile"
      :mini-width="56"
      :width="232"
      :behavior="isMobile ? 'mobile' : 'desktop'"
      class="app-sidebar"
      @mouseover="onDrawerMouseOver"
      @mouseout="onDrawerMouseOut"
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
      <SafetyStatusBanner />
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

<script lang="ts">
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import axios from 'axios'
import { LocalStorage, useQuasar } from 'quasar'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import DrawerMainNav from 'components/drawers/DrawerMainNav.vue'
import ThemeSwitch from 'components/ThemeSwitch.vue'
import PaletteSwitch from 'components/PaletteSwitch.vue'
import DrawerNotifications from 'components/drawers/DrawerNotifications.vue'
import SharedLinkDropdown from 'components/SharedLinkDropdown.vue'
import SafetyStatusBanner from 'components/SafetyStatusBanner.vue'
import KeyboardShortcutsDialog from 'components/ui/KeyboardShortcutsDialog.vue'
import FirstRunWizard from 'components/ui/FirstRunWizard.vue'
import compressoGlobals, { getCompressoApiUrl, notificationsCount } from 'src/js/compressoGlobals'
import { wsConnectionState } from 'src/js/compressoWebsocket'
import { useKeyboardShortcuts } from 'src/composables/useKeyboardShortcuts'
import { createLogger } from 'src/composables/useLogger'
import type { LiveGpuMetrics, SystemStatus } from 'src/types/contracts'

type LiveSystemStatus = Omit<SystemStatus, 'gpus'> & { gpus: LiveGpuMetrics[] }
interface TopBarMetrics {
  cpu: number
  mem: number
  gpu: number | null
}

const PAGE_HEADER_KEYS: Record<string, string> = {
  '/ui/dashboard': 'dashboard',
  '/ui/compression': 'compression',
  '/ui/approval': 'approval',
  '/ui/preview': 'preview',
  '/ui/health': 'health',
  '/ui/readiness': 'readiness',
  '/ui/history': 'history',
  '/ui/data-panels': 'dataPanels',
  '/ui/settings-library': 'settings',
  '/ui/settings-workers': 'settings',
  '/ui/settings-plugins': 'settings',
  '/ui/settings-link': 'settings',
  '/ui/settings-notifications': 'settings',
}

export default {
  components: {
    DrawerMainNav,
    DrawerNotifications,
    ThemeSwitch,
    PaletteSwitch,
    SharedLinkDropdown,
    SafetyStatusBanner,
    KeyboardShortcutsDialog,
    FirstRunWizard,
  },
  setup() {
    const $q = useQuasar()
    const route = useRoute()
    const { t } = useI18n()
    const log = createLogger('MainLayout')

    // Sidebar state
    const leftDrawerOpen = ref(!$q.screen.lt.md)
    // Expanded (pinned) by default — matches the polished fixed-sidebar design
    const sidebarPinned = ref(LocalStorage.getItem('sidebar_pinned') !== false)
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

    function onPinToggle(val: boolean): void {
      sidebarPinned.value = val
      LocalStorage.set('sidebar_pinned', val)
    }

    // Page header (title + subtitle) derived from route
    const pageTitle = computed(() => {
      const key = PAGE_HEADER_KEYS[route.path]
      return key ? t(`pageHeaders.${key}.title`) : 'Compresso'
    })
    const pageSubtitle = computed(() => {
      const key = PAGE_HEADER_KEYS[route.path]
      return key ? t(`pageHeaders.${key}.subtitle`) : ''
    })

    // Top bar system meters (polled — independent of page websockets)
    const systemMetrics = ref<TopBarMetrics>({ cpu: 0, mem: 0, gpu: null })
    let metricsInterval: ReturnType<typeof setInterval> | null = null

    function meterColor(percent: number): string {
      if (percent >= 85) return 'var(--q-negative)'
      if (percent >= 50) return 'var(--q-warning)'
      return 'var(--q-positive)'
    }

    const meters = computed(() => {
      const list = [
        { label: 'CPU', percent: Math.round(systemMetrics.value.cpu) },
        { label: 'MEM', percent: Math.round(systemMetrics.value.mem) },
      ]
      if (systemMetrics.value.gpu != null) {
        list.push({ label: 'GPU', percent: Math.round(systemMetrics.value.gpu) })
      }
      return list.map((m) => ({ ...m, color: meterColor(m.percent) }))
    })

    async function fetchSystemMetrics() {
      try {
        const response = await axios.get<LiveSystemStatus>(getCompressoApiUrl('v2', 'system/status'))
        const gpus = response.data.gpus || []
        const firstGpu = gpus[0]
        systemMetrics.value = {
          cpu: response.data.cpu?.percent || 0,
          mem: response.data.memory?.percent || 0,
          gpu: firstGpu?.utilization_percent ?? null,
        }
      } catch (err) {
        log.debug('Failed to fetch system metrics for top bar: ' + err)
      }
    }

    // Connection indicator
    const connectionState = computed(() => wsConnectionState.value)
    const connectionTextClass = computed(() => {
      switch (connectionState.value) {
        case 'connected':
          return 'text-positive'
        case 'connecting':
          return 'text-warning'
        default:
          return 'text-negative'
      }
    })
    const connectionLabel = computed(() => {
      switch (connectionState.value) {
        case 'connected':
          return t('systemStatus.live')
        case 'connecting':
          return t('systemStatus.connecting')
        default:
          return t('systemStatus.offline')
      }
    })

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

      // Top bar meters
      fetchSystemMetrics()
      metricsInterval = setInterval(fetchSystemMetrics, 5000)

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

    onUnmounted(() => {
      if (metricsInterval) clearInterval(metricsInterval)
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
      pageTitle,
      pageSubtitle,
      meters,
      connectionState,
      connectionTextClass,
      connectionLabel,
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
