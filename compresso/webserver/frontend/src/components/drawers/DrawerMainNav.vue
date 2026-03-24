<template>
  <div class="column fit drawer-background">
    <!-- Profile Section -->
    <div :class="{'q-pt-xl' : !$q.screen.gt.sm}">
      <DrawerUserProfileHeader/>
    </div>

    <!-- Scrollable Navigation -->
    <q-scroll-area class="col">
      <q-list padding>

        <!--START DASHBOARD SELECT-->
        <q-item
          clickable
          to="/ui/dashboard"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/dashboard' }">
          <q-item-section avatar>
            <q-icon name="dashboard"/>
          </q-item-section>
          <q-item-section>
            {{ $t('navigation.dashboard') }}
          </q-item-section>
        </q-item>
        <!--END DASHBOARD SELECT-->
        <!--START SETTINGS SELECT-->
        <q-expansion-item
          icon="settings"
          :label="$t('navigation.settings')"
          :default-opened="isSettingsRoute"
          :header-class="isSettingsRoute ? 'text-primary text-weight-bold' : ''"
        >
          <q-item clickable to="/ui/settings-library" v-ripple :active="$route.path === '/ui/settings-library'" dense class="q-pl-xl">
            <q-item-section avatar><q-icon name="account_tree" size="sm"/></q-item-section>
            <q-item-section>{{ $t('navigation.library') }}</q-item-section>
          </q-item>
          <q-item clickable to="/ui/settings-workers" v-ripple :active="$route.path === '/ui/settings-workers'" dense class="q-pl-xl">
            <q-item-section avatar><q-icon name="engineering" size="sm"/></q-item-section>
            <q-item-section>{{ $t('navigation.workers') }}</q-item-section>
          </q-item>
          <q-item clickable to="/ui/settings-plugins" v-ripple :active="$route.path === '/ui/settings-plugins'" dense class="q-pl-xl">
            <q-item-section avatar><q-icon name="extension" size="sm"/></q-item-section>
            <q-item-section>{{ $t('navigation.plugins') }}</q-item-section>
          </q-item>
          <q-item clickable to="/ui/settings-link" v-ripple :active="$route.path === '/ui/settings-link'" dense class="q-pl-xl">
            <q-item-section avatar><q-icon name="link" size="sm"/></q-item-section>
            <q-item-section>{{ $t('navigation.link') }}</q-item-section>
          </q-item>
        </q-expansion-item>
        <!--END SETTINGS SELECT-->
        <!--START DATA PANELS SELECT-->
        <q-expansion-item
          icon="insights"
          :label="$t('navigation.dataPanels')"
          :default-opened="isDataPanelsRoute"
          :header-class="isDataPanelsRoute ? 'text-primary text-weight-bold' : ''"
        >
          <q-item clickable to="/ui/data-panels" v-ripple :active="$route.path === '/ui/data-panels' && !$route.query.pluginId" dense class="q-pl-xl">
            <q-item-section avatar><q-icon name="insights" size="sm"/></q-item-section>
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
            <q-item-section avatar><q-icon name="bar_chart" size="sm"/></q-item-section>
            <q-item-section>{{ panel.label }}</q-item-section>
          </q-item>
        </q-expansion-item>
        <!--END DATA PANELS SELECT-->
        <q-item-label header class="text-caption text-weight-medium" style="padding: 12px 16px 4px">{{ $t('navigation.tools') }}</q-item-label>
        <!--START COMPRESSION DASHBOARD SELECT-->
        <q-item
          clickable
          to="/ui/compression"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/compression' }">
          <q-item-section avatar>
            <q-icon name="compress"/>
          </q-item-section>
          <q-item-section>
            {{ $t('navigation.compression') }}
          </q-item-section>
        </q-item>
        <!--END COMPRESSION DASHBOARD SELECT-->
        <!--START APPROVAL QUEUE SELECT-->
        <q-item
          clickable
          to="/ui/approval"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/approval' }">
          <q-item-section avatar>
            <q-icon name="fact_check"/>
          </q-item-section>
          <q-item-section>
            {{ $t('navigation.approvalQueue') }}
            <q-badge
              v-if="approvalCount > 0"
              color="orange"
              floating
              :label="approvalCount"/>
          </q-item-section>
        </q-item>
        <!--END APPROVAL QUEUE SELECT-->
        <!--START PREVIEW COMPARE SELECT-->
        <q-item
          clickable
          to="/ui/preview"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/preview' }">
          <q-item-section avatar>
            <q-icon name="compare"/>
          </q-item-section>
          <q-item-section>
            {{ $t('navigation.abPreview') }}
          </q-item-section>
        </q-item>
        <!--END PREVIEW COMPARE SELECT-->
        <!--START HEALTH CHECK SELECT-->
        <q-item
          clickable
          to="/ui/health"
          v-ripple
          :class="{ 'nav-active': $route.path === '/ui/health' }">
          <q-item-section avatar>
            <q-icon name="health_and_safety"/>
          </q-item-section>
          <q-item-section>
            {{ $t('navigation.healthCheck') }}
          </q-item-section>
        </q-item>
        <!--END HEALTH CHECK SELECT-->

        <q-separator spaced/>

        <!--START THEME SELECT (MOBILE ONLY)-->
        <q-item v-if="$q.screen.lt.sm">
          <q-item-section avatar>
            <q-icon name="palette"/>
          </q-item-section>
          <q-item-section>
            {{ $t('navigation.theme') }}
          </q-item-section>
          <q-item-section side>
            <ThemeSwitch/>
          </q-item-section>
        </q-item>
        <!--END THEME SELECT (MOBILE ONLY)-->

        <q-separator spaced/>

        <q-item-label header>{{ $t('navigation.documentation') }}:</q-item-label>
        <!--START SUPPORT SELECT-->
        <q-item
          clickable
          @click="showHelpSupportDialog"
          v-ripple>
          <q-item-section avatar>
            <q-icon name="fa-regular fa-life-ring"/>
          </q-item-section>
          <q-item-section>
            {{ $t('navigation.helpAndSupport') }}
          </q-item-section>
        </q-item>
        <!--END SUPPORT SELECT-->

        <!--START APPLICATION LOGS-->
        <q-item
          clickable
          @click="showApplicationLogsDialog"
          v-ripple>
          <q-item-section avatar>
            <q-icon name="article"/>
          </q-item-section>
          <q-item-section>
            {{ $t('navigation.applicationLogs') }}
          </q-item-section>
        </q-item>
        <!--END APPLICATION LOGS-->

        <!--START PRIVACY POLICY-->
        <q-item
          clickable
          @click="showPrivacyPolicyDialog"
          v-ripple>
          <q-item-section avatar>
            <q-icon name="o_shield"/>
          </q-item-section>
          <q-item-section>
            {{ $t('headers.privacyPolicy') }}
          </q-item-section>
        </q-item>
        <!--END PRIVACY POLICY-->

      </q-list>
    </q-scroll-area>

    <!-- Footer Section (Mobile Only) -->
    <div class="lt-md">
      <q-img src="~assets/bg-design-3.png" style="height: 80px">
        <div class="absolute-full footer-gradient"></div>
        <div class="absolute-full bg-transparent text-white row items-center q-px-md">
          <FooterData/>
        </div>
      </q-img>
    </div>

    <!-- Dialogs -->
    <HelpSupportDialog ref="helpSupportDialogRef"/>
    <ApplicationLogsDialog ref="applicationLogsDialogRef"/>
    <PrivacyPolicyDialog ref="privacyPolicyDialogRef"/>
  </div>
</template>

<script>

import DrawerUserProfileHeader from "components/drawers/partials/DrawerUserProfileHeader.vue";
import ThemeSwitch from "components/ThemeSwitch";
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import axios from "axios";
import { getCompressoApiUrl } from "src/js/compressoGlobals";
import FooterData from "components/FooterData";
import PrivacyPolicyDialog from "components/docs/PrivacyPolicyDialog.vue";
import HelpSupportDialog from "components/docs/HelpSupportDialog.vue";
import ApplicationLogsDialog from "components/docs/ApplicationLogsDialog.vue";

export default {
  name: 'DrawerMainNav',
  components: {
    DrawerUserProfileHeader,
    FooterData,
    ThemeSwitch,
    HelpSupportDialog,
    ApplicationLogsDialog,
    PrivacyPolicyDialog,
  },
  setup() {
    const route = useRoute();
    const privacyPolicyDialogRef = ref(null);
    const helpSupportDialogRef = ref(null);
    const applicationLogsDialogRef = ref(null);
    const approvalCount = ref(0);
    const availableDataPanels = ref([]);
    let approvalInterval = null;

    const isSettingsRoute = computed(() => route.path.startsWith('/ui/settings'));
    const isDataPanelsRoute = computed(() => route.path === '/ui/data-panels');

    async function fetchDataPanelList() {
      try {
        const response = await axios.get(getCompressoApiUrl('v2', 'plugins/panels/enabled'));
        availableDataPanels.value = (response.data.results || []).map(p => ({
          id: p.plugin_id,
          label: p.name,
        }));
      } catch {
        // Silently ignore
      }
    }

    function showPrivacyPolicyDialog() {
      if (privacyPolicyDialogRef.value) {
        privacyPolicyDialogRef.value.show()
      }
    }

    function showHelpSupportDialog() {
      if (helpSupportDialogRef.value) {
        helpSupportDialogRef.value.show()
      }
    }

    function showApplicationLogsDialog() {
      if (applicationLogsDialogRef.value) {
        applicationLogsDialogRef.value.show()
      }
    }

    async function fetchApprovalCount() {
      try {
        const res = await axios.get('/compresso/api/v2/approval/count');
        approvalCount.value = res.data.count || 0;
      } catch (e) {
        // Silently ignore — endpoint may not exist if approval is disabled
      }
    }

    onMounted(() => {
      fetchApprovalCount();
      fetchDataPanelList();
      approvalInterval = setInterval(fetchApprovalCount, 15000);
    });

    onUnmounted(() => {
      if (approvalInterval) {
        clearInterval(approvalInterval);
      }
    });

    return {
      showPrivacyPolicyDialog,
      showHelpSupportDialog,
      showApplicationLogsDialog,
      privacyPolicyDialogRef,
      helpSupportDialogRef,
      applicationLogsDialogRef,
      approvalCount,
      availableDataPanels,
      isSettingsRoute,
      isDataPanelsRoute,
    }
  },
}
</script>

<style scoped>
.footer-gradient {
  background: linear-gradient(to top, #13291f, rgba(19, 41, 31, 0.7)) !important;
}

.nav-active {
  border-left: 3px solid var(--q-primary);
  background: rgba(26, 107, 74, 0.08);
}

.body--dark .nav-active {
  background: rgba(34, 145, 106, 0.12);
}
</style>
