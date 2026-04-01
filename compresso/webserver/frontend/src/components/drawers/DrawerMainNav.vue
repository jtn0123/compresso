<template>
  <div class="column fit">
    <!-- Pin toggle (only visible when expanded) -->
    <div v-if="!mini" class="row items-center justify-end q-px-sm q-pt-sm" style="min-height: 32px">
      <q-btn
        dense
        flat
        round
        size="xs"
        :icon="pinned ? 'push_pin' : 'push_pin'"
        :color="pinned ? 'primary' : 'grey-6'"
        :style="{ transform: pinned ? 'none' : 'rotate(45deg)' }"
        @click="$emit('update:pinned', !pinned)"
      >
        <q-tooltip>{{ pinned ? 'Unpin sidebar' : 'Pin sidebar' }}</q-tooltip>
      </q-btn>
    </div>
    <div v-else style="height: 8px" />

    <!-- Scrollable Navigation -->
    <q-scroll-area class="col">
      <q-list dense>
        <!-- Dashboard -->
        <q-item clickable to="/ui/dashboard" v-ripple :class="{ 'nav-active': $route.path === '/ui/dashboard' }">
          <q-item-section avatar>
            <q-icon name="dashboard" size="20px" />
          </q-item-section>
          <q-item-section v-if="!mini">
            {{ $t('navigation.dashboard') }}
          </q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.dashboard') }}</q-tooltip>
        </q-item>

        <q-separator class="q-my-xs q-mx-sm" />

        <!-- CORE TOOLS -->
        <q-item-label v-if="!mini" class="nav-section-label">{{ $t('navigation.tools') }}</q-item-label>

        <q-item clickable to="/ui/compression" v-ripple :class="{ 'nav-active': $route.path === '/ui/compression' }">
          <q-item-section avatar><q-icon name="compress" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.compression') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.compression') }}</q-tooltip>
        </q-item>

        <q-item clickable to="/ui/approval" v-ripple :class="{ 'nav-active': $route.path === '/ui/approval' }">
          <q-item-section avatar><q-icon name="fact_check" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">
            {{ $t('navigation.approvalQueue') }}
          </q-item-section>
          <q-badge v-if="approvalCount > 0" color="orange" floating :label="approvalCount" />
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{
            $t('navigation.approvalQueue')
          }}</q-tooltip>
        </q-item>

        <q-item clickable to="/ui/preview" v-ripple :class="{ 'nav-active': $route.path === '/ui/preview' }">
          <q-item-section avatar><q-icon name="compare" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.abPreview') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.abPreview') }}</q-tooltip>
        </q-item>

        <q-separator class="q-my-xs q-mx-sm" />

        <!-- MONITORING -->
        <q-item-label v-if="!mini" class="nav-section-label">{{
          $t('navigation.monitoring') || 'Monitoring'
        }}</q-item-label>

        <q-item clickable to="/ui/health" v-ripple :class="{ 'nav-active': $route.path === '/ui/health' }">
          <q-item-section avatar><q-icon name="health_and_safety" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.healthCheck') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.healthCheck') }}</q-tooltip>
        </q-item>

        <q-item clickable to="/ui/history" v-ripple :class="{ 'nav-active': $route.path === '/ui/history' }">
          <q-item-section avatar><q-icon name="history" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.history') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.history') }}</q-tooltip>
        </q-item>

        <!-- Data Panels: expandable when not mini, popup menu when mini -->
        <q-item v-if="mini" clickable v-ripple :class="{ 'nav-active': $route.path === '/ui/data-panels' }">
          <q-item-section avatar><q-icon name="insights" size="20px" /></q-item-section>
          <q-tooltip anchor="center right" self="center left">{{ $t('navigation.dataPanels') }}</q-tooltip>
          <q-menu anchor="top right" self="top left" :offset="[4, 0]">
            <q-list dense style="min-width: 150px">
              <q-item clickable to="/ui/data-panels" v-close-popup v-ripple>
                <q-item-section>{{ $t('navigation.dataPanels') }}</q-item-section>
              </q-item>
              <q-item
                v-for="panel in availableDataPanels"
                :key="panel.id"
                clickable
                @click="$router.push('/ui/data-panels?pluginId=' + panel.id)"
                v-close-popup
                v-ripple
              >
                <q-item-section>{{ panel.label }}</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-item>

        <q-expansion-item
          v-if="!mini"
          icon="insights"
          :label="$t('navigation.dataPanels')"
          :default-opened="isDataPanelsRoute"
          :header-class="isDataPanelsRoute ? 'text-primary text-weight-bold' : ''"
          dense
        >
          <q-item
            clickable
            to="/ui/data-panels"
            v-ripple
            :active="$route.path === '/ui/data-panels' && !$route.query.pluginId"
            dense
            class="q-pl-xl"
          >
            <q-item-section avatar><q-icon name="insights" size="sm" /></q-item-section>
            <q-item-section>{{ $t('navigation.dataPanels') }}</q-item-section>
          </q-item>
          <q-item
            v-for="panel in availableDataPanels"
            :key="panel.id"
            clickable
            @click="$router.push('/ui/data-panels?pluginId=' + panel.id)"
            v-ripple
            :active="$route.query.pluginId === panel.id"
            dense
            class="q-pl-xl"
          >
            <q-item-section avatar><q-icon name="bar_chart" size="sm" /></q-item-section>
            <q-item-section>{{ panel.label }}</q-item-section>
          </q-item>
        </q-expansion-item>

        <q-separator class="q-my-xs q-mx-sm" />

        <!-- SETTINGS (flat list) -->
        <q-item-label v-if="!mini" class="nav-section-label">{{ $t('navigation.settings') }}</q-item-label>

        <q-item
          clickable
          to="/ui/settings-library"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/settings-library' }"
        >
          <q-item-section avatar><q-icon name="account_tree" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.library') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.library') }}</q-tooltip>
        </q-item>

        <q-item
          clickable
          to="/ui/settings-workers"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/settings-workers' }"
        >
          <q-item-section avatar><q-icon name="engineering" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.workers') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.workers') }}</q-tooltip>
        </q-item>

        <q-item
          clickable
          to="/ui/settings-plugins"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/settings-plugins' }"
        >
          <q-item-section avatar><q-icon name="extension" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.plugins') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.plugins') }}</q-tooltip>
        </q-item>

        <q-item
          clickable
          to="/ui/settings-link"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/settings-link' }"
        >
          <q-item-section avatar><q-icon name="link" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.link') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{ $t('navigation.link') }}</q-tooltip>
        </q-item>

        <q-item
          clickable
          to="/ui/settings-notifications"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/settings-notifications' }"
        >
          <q-item-section avatar><q-icon name="notifications_active" size="20px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.notifications') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{
            $t('navigation.notifications')
          }}</q-tooltip>
        </q-item>
      </q-list>
    </q-scroll-area>

    <!-- Bottom section -->
    <div class="q-pa-xs">
      <q-separator class="q-mb-xs" />

      <!-- Help/Docs items -->
      <q-list dense>
        <q-item clickable @click="showHelpSupportDialog" v-ripple>
          <q-item-section avatar><q-icon name="fa-regular fa-life-ring" size="18px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.helpAndSupport') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{
            $t('navigation.helpAndSupport')
          }}</q-tooltip>
        </q-item>

        <q-item clickable @click="showApplicationLogsDialog" v-ripple>
          <q-item-section avatar><q-icon name="article" size="18px" /></q-item-section>
          <q-item-section v-if="!mini">{{ $t('navigation.applicationLogs') }}</q-item-section>
          <q-tooltip v-if="mini" anchor="center right" self="center left">{{
            $t('navigation.applicationLogs')
          }}</q-tooltip>
        </q-item>

        <!-- Mobile-only theme/palette controls -->
        <template v-if="$q.screen.lt.sm && !mini">
          <q-item>
            <q-item-section avatar><q-icon name="palette" size="18px" /></q-item-section>
            <q-item-section>
              <div class="row items-center q-gutter-xs">
                <ThemeSwitch />
                <PaletteSwitch />
              </div>
            </q-item-section>
          </q-item>
        </template>
      </q-list>

      <!-- Version -->
      <div class="text-center q-py-xs">
        <span
          class="text-caption"
          style="
            opacity: 0.4;
            font-size: 0.6rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            display: block;
          "
          >v{{ compressoVersion }}</span
        >
      </div>
    </div>

    <!-- Dialogs -->
    <HelpSupportDialog ref="helpSupportDialogRef" />
    <ApplicationLogsDialog ref="applicationLogsDialogRef" />
    <PrivacyPolicyDialog ref="privacyPolicyDialogRef" />
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import compressoGlobals from 'src/js/compressoGlobals'
import ThemeSwitch from 'components/ThemeSwitch'
import PaletteSwitch from 'components/PaletteSwitch'
import PrivacyPolicyDialog from 'components/docs/PrivacyPolicyDialog.vue'
import HelpSupportDialog from 'components/docs/HelpSupportDialog.vue'
import ApplicationLogsDialog from 'components/docs/ApplicationLogsDialog.vue'

export default {
  name: 'DrawerMainNav',
  components: {
    ThemeSwitch,
    PaletteSwitch,
    HelpSupportDialog,
    ApplicationLogsDialog,
    PrivacyPolicyDialog,
  },
  props: {
    mini: { type: Boolean, default: false },
    pinned: { type: Boolean, default: true },
  },
  emits: ['update:pinned'],
  setup() {
    const route = useRoute()
    const privacyPolicyDialogRef = ref(null)
    const helpSupportDialogRef = ref(null)
    const applicationLogsDialogRef = ref(null)
    const approvalCount = ref(0)
    const availableDataPanels = ref([])
    const compressoVersion = ref('')
    let approvalInterval = null

    const isDataPanelsRoute = computed(() => route.path === '/ui/data-panels')

    async function fetchDataPanelList() {
      try {
        const response = await axios.get(getCompressoApiUrl('v2', 'plugins/panels/enabled'))
        availableDataPanels.value = (response.data.results || []).map((p) => ({
          id: p.plugin_id,
          label: p.name,
        }))
      } catch {
        // Silently ignore
      }
    }

    function showPrivacyPolicyDialog() {
      if (privacyPolicyDialogRef.value) privacyPolicyDialogRef.value.show()
    }

    function showHelpSupportDialog() {
      if (helpSupportDialogRef.value) helpSupportDialogRef.value.show()
    }

    function showApplicationLogsDialog() {
      if (applicationLogsDialogRef.value) applicationLogsDialogRef.value.show()
    }

    async function fetchApprovalCount() {
      try {
        const res = await axios.get('/compresso/api/v2/approval/count')
        approvalCount.value = res.data.count || 0
      } catch {
        // Silently ignore
      }
    }

    onMounted(() => {
      fetchApprovalCount()
      fetchDataPanelList()
      approvalInterval = setInterval(fetchApprovalCount, 15000)
      compressoGlobals.getCompressoVersion().then((version) => {
        compressoVersion.value = version
      })
    })

    onUnmounted(() => {
      if (approvalInterval) clearInterval(approvalInterval)
    })

    return {
      showPrivacyPolicyDialog,
      showHelpSupportDialog,
      showApplicationLogsDialog,
      privacyPolicyDialogRef,
      helpSupportDialogRef,
      applicationLogsDialogRef,
      approvalCount,
      availableDataPanels,
      isDataPanelsRoute,
      compressoVersion,
    }
  },
}
</script>

<style scoped>
.q-item {
  border-radius: 6px;
  margin: 1px 6px;
  min-height: 36px;
}

.q-item .q-icon {
  color: var(--compresso-grey-6);
}
</style>
