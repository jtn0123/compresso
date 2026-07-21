<template>
  <q-page padding class="page-with-mobile-quick-nav">
    <!-- content -->

    <div class="q-pa-none">
      <div class="row">
        <div class="col-sm-12 col-md-10 col-lg-8">
          <div :class="$q.screen.lt.md ? 'q-ma-sm' : 'q-ma-sm q-pa-md'">
            <q-form @submit="save" class="q-gutter-md">
              <!--START THIS INSTALLATION-->
              <h5 class="q-mb-none">{{ $t('components.settings.link.thisInstallation') }}</h5>
              <div class="q-gutter-sm">
                <q-skeleton v-if="installationName === null" type="QInput" />
                <q-input
                  v-if="installationName !== null"
                  outlined
                  color="primary"
                  v-model="installationName"
                  :label="$t('components.settings.link.nameThisInstall')"
                  :placeholder="installationName"
                >
                </q-input>
                <q-skeleton v-if="installationPublicAddress === null" type="QInput" />
                <q-input
                  v-if="installationPublicAddress !== null"
                  outlined
                  color="primary"
                  v-model="installationPublicAddress"
                  :label="$t('components.settings.link.installationPublicAddress')"
                  :placeholder="installationPublicAddress"
                  :rules="[
                    (val) =>
                      !val ||
                      val.toLowerCase().startsWith('http') ||
                      $t('components.settings.link.addressMustStartWithHttp'),
                  ]"
                >
                </q-input>
              </div>

              <AdmonitionBanner type="note" class="q-mt-md">
                <p>{{ $t('components.settings.link.syncTipBody') }}</p>
              </AdmonitionBanner>
              <!--END THIS INSTALLATION-->

              <q-separator class="q-my-lg" />

              <!--START REMOTE INSTALLATIONS-->
              <h5 class="q-mb-none">{{ $t('components.settings.link.remoteInstallations') }}</h5>
              <div class="q-gutter-sm">
                <q-skeleton v-if="remoteInstallations === null" type="text" />

                <q-list bordered separator class="rounded-borders">
                  <q-item v-for="(installation, index) in remoteInstallations" :key="index">
                    <q-item-section avatar>
                      <q-img v-if="installation.available" src="~assets/compresso-logo-white.png" />
                      <q-img v-else :img-style="{ filter: 'grayscale(100%)' }" src="~assets/compresso-logo-white.png" />
                      <q-tooltip v-if="installation.available">
                        {{ $t('tooltips.available') }}
                      </q-tooltip>
                      <q-tooltip v-else>
                        {{ $t('tooltips.unavailable') }}
                      </q-tooltip>
                    </q-item-section>

                    <q-separator inset vertical class="q-mr-sm" />

                    <q-item-section class="q-px-sm q-mx-sm">
                      <!--Link Address-->
                      <q-item-label lines="1">
                        {{ installation.address }}
                      </q-item-label>

                      <!--Link Name-->
                      <q-item-label caption lines="2">
                        <div class="row q-mt-sm">
                          <div class="col-3">
                            <span class="text-weight-bold">{{ $t('components.settings.link.name') }}:</span>
                          </div>
                          <div class="col-grow">
                            <span class="q-pl-none">{{ installation.name }}</span>
                          </div>
                        </div>
                      </q-item-label>

                      <!--Link Version-->
                      <q-item-label caption lines="2">
                        <div class="row">
                          <div class="col-3">
                            <span class="text-weight-bold">{{ $t('components.settings.link.version') }}:</span>
                          </div>
                          <div class="col-grow">
                            <span class="q-pl-none">{{ installation.version }}</span>
                          </div>
                        </div>
                      </q-item-label>
                    </q-item-section>

                    <q-item-section v-if="!$q.screen.lt.md">
                      <q-item-label lines="1">
                        <div class="row">
                          <div class="col-6 text-left">
                            <span :class="installation.enableReceivingTasks ? 'text-primary' : 'text-grey-8'">
                              <q-icon v-if="installation.enableReceivingTasks" color="check" name="check" />
                              <q-icon v-else color="close" name="close" />
                              |
                              {{ $t('components.settings.link.linkReceivingTasksStatusLabel') }}
                            </span>
                          </div>
                        </div>
                      </q-item-label>
                      <q-item-label lines="1">
                        <div class="row">
                          <div class="col-6 text-left">
                            <span :class="installation.enableSendingTasks ? 'text-primary' : 'text-grey-8'">
                              <q-icon v-if="installation.enableSendingTasks" color="check" name="check" />
                              <q-icon v-else color="close" name="close" />
                              |
                              {{ $t('components.settings.link.linkSendingTasksStatusLabel') }}
                            </span>
                          </div>
                        </div>
                      </q-item-label>
                      <q-item-label v-if="installation.enableSendingTasks" lines="1">
                        <div class="row">
                          <div class="col-6 text-left">
                            <span :class="installation.enableTaskPreloading ? 'text-primary' : 'text-grey-8'">
                              <q-icon v-if="installation.enableTaskPreloading" color="check" name="check" />
                              <q-icon v-else color="close" name="close" />
                              |
                              {{ $t('components.settings.link.linkPreloadRemoteTasksStatusLabel') }}
                            </span>
                          </div>
                        </div>
                      </q-item-label>
                      <q-item-label v-if="installation.enableSendingTasks" lines="1">
                        <div class="row">
                          <div class="col-6 text-left">
                            <span :class="installation.enableChecksumValidation ? 'text-primary' : 'text-grey-8'">
                              <q-icon v-if="installation.enableChecksumValidation" color="check" name="check" />
                              <q-icon v-else color="close" name="close" />
                              |
                              {{ $t('components.settings.link.linkConfigChecksumValidationStatusLabel') }}
                            </span>
                          </div>
                        </div>
                      </q-item-label>
                      <q-item-label v-if="installation.enableSendingTasks" lines="1">
                        <div class="row">
                          <div class="col-6 text-left">
                            <span :class="installation.enableConfigMissingLibraries ? 'text-primary' : 'text-grey-8'">
                              <q-icon v-if="installation.enableConfigMissingLibraries" color="check" name="check" />
                              <q-icon v-else color="close" name="close" />
                              |
                              {{ $t('components.settings.link.linkConfigRemoteLibrariesStatusLabel') }}
                            </span>
                          </div>
                        </div>
                      </q-item-label>
                      <q-item-label lines="1">
                        <div class="row">
                          <div class="col-6 text-left">
                            <span :class="installation.enableDistributedWorkers ? 'text-primary' : 'text-grey-8'">
                              <q-icon v-if="installation.enableDistributedWorkers" color="check" name="check" />
                              <q-icon v-else color="close" name="close" />
                              |
                              {{ $t('components.settings.link.linkDistributedWorkersStatusLabel') }}
                            </span>
                          </div>
                        </div>
                      </q-item-label>
                    </q-item-section>

                    <q-separator inset vertical class="q-mx-sm" />

                    <q-item-section center side>
                      <div class="text-grey-8 q-gutter-xs">
                        <CompressoListActionButton
                          icon="tune"
                          color="grey-8"
                          :tooltip="$t('tooltips.configure')"
                          @click="configureRemoteInstallation(index)"
                        />
                        <CompressoListActionButton
                          icon="delete"
                          color="negative"
                          :tooltip="$t('tooltips.delete')"
                          @click="deleteRemoteInstallation(index)"
                        />
                      </div>
                    </q-item-section>
                  </q-item>
                </q-list>

                <q-bar class="bg-transparent">
                  <q-space />
                  <CompressoListAddButton :tooltip="$t('tooltips.add')" @click="openNewRemoteInstallationDialog" />
                </q-bar>

                <CompressoDialogPopup
                  ref="addRemoteDialogRef"
                  :title="$t('components.settings.link.addRemoteInstallation')"
                  :mini="true"
                  :actions="addRemoteDialogActions"
                  @add="addNewRemoteInstallation"
                >
                  <div class="q-pa-md">
                    <q-input
                      outlined
                      color="primary"
                      v-model="newRemoteInstallationAddress"
                      :label="$t('components.settings.link.address')"
                      placeholder="192.168.1.2:8888"
                      class="q-mb-md"
                    />

                    <q-select
                      outlined
                      v-model="newRemoteInstallationAuthenticationType"
                      :options="newRemoteInstallationAuthenticationOptions"
                      :label="$t('components.settings.link.authentication')"
                      class="q-mb-md"
                    />

                    <template v-if="newRemoteInstallationAuthenticationType !== 'None'">
                      <q-input
                        outlined
                        color="primary"
                        v-model="newRemoteInstallationUsername"
                        :label="$t('components.settings.link.username')"
                        class="q-mb-md"
                      />

                      <q-input
                        outlined
                        color="primary"
                        v-model="newRemoteInstallationPassword"
                        :label="$t('components.settings.link.password')"
                      />
                    </template>

                    <q-input
                      outlined
                      color="primary"
                      v-model="newRemoteInstallationApiToken"
                      type="password"
                      :label="$t('components.settings.link.apiToken')"
                      :hint="$t('components.settings.link.apiTokenHint')"
                      class="q-mt-md"
                    />
                  </div>
                </CompressoDialogPopup>
              </div>
              <!--END REMOTE INSTALLATIONS-->

              <q-separator class="q-my-lg" />

              <div>
                <CompressoSettingsSubmitButton />
              </div>
            </q-form>
          </div>
        </div>
      </div>

      <RemoteInstallLinkDialog
        ref="remoteInstallDialogRef"
        :uuid="activeRemoteInstallationUuid"
        @saved="onRemoteInstallSaved"
        @hide="onRemoteInstallHide"
      />

      <MobileSettingsQuickNav
        :prev-enabled="true"
        :prev-label="$t('navigation.plugins')"
        :prev-path="'/ui/settings-plugins'"
        :next-enabled="true"
        :next-label="$t('navigation.notifications')"
        :next-path="'/ui/settings-notifications'"
      />
    </div>
  </q-page>
</template>

<script lang="ts">
import { CompressoWebsocketHandler } from 'src/js/compressoWebsocket'
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { createLogger } from 'src/composables/useLogger'
import RemoteInstallLinkDialog from 'components/settings/link/RemoteInstallLinkDialog.vue'
import MobileSettingsQuickNav from 'components/MobileSettingsQuickNav.vue'
import AdmonitionBanner from 'components/ui/AdmonitionBanner.vue'
import CompressoSettingsSubmitButton from 'components/ui/buttons/CompressoSettingsSubmitButton.vue'
import CompressoListActionButton from 'components/ui/buttons/CompressoListActionButton.vue'
import CompressoListAddButton from 'components/ui/buttons/CompressoListAddButton.vue'
import CompressoDialogPopup from 'components/ui/dialogs/CompressoDialogPopup.vue'
import type { DialogController } from 'src/types/ui'

interface RemoteInstallationView {
  address: string
  auth?: string
  username?: string | null
  password?: string | null
  api_token?: string | null
  enableReceivingTasks: boolean
  enableSendingTasks: boolean
  enableTaskPreloading: boolean
  enableChecksumValidation: boolean
  enableConfigMissingLibraries: boolean
  enableDistributedWorkers: boolean
  name: string
  version: string
  uuid: string
  available: boolean
}

const log = createLogger('SettingsLink')

export default {
  name: 'SettingsLink',
  components: {
    RemoteInstallLinkDialog,
    MobileSettingsQuickNav,
    AdmonitionBanner,
    CompressoSettingsSubmitButton,
    CompressoListActionButton,
    CompressoListAddButton,
    CompressoDialogPopup,
  },
  setup() {
    const { t: $t } = useI18n()
    const addRemoteDialogRef = ref<DialogController | null>(null)

    /**
     * Compresso WS handle
     * @type {null}
     */
    const compressoWSHandler = CompressoWebsocketHandler($t)

    function initCompressoWebsocket() {
      compressoWSHandler.init()
    }

    function closeCompressoWebsocket() {
      compressoWSHandler.close()
    }

    // END COMPRESSO WS HANDLE

    onMounted(() => {
      // Start the websocket
      initCompressoWebsocket()
    })
    onUnmounted(() => {
      // Close the websocket
      closeCompressoWebsocket()
    })

    return {
      addRemoteDialogRef,
    }
  },
  data() {
    return {
      installationName: null as string | null,
      installationPublicAddress: null as string | null,
      remoteInstallations: [] as RemoteInstallationView[],
      newRemoteInstallation: false,
      newRemoteInstallationAddress: '',
      newRemoteInstallationAuthenticationType: 'None',
      newRemoteInstallationAuthenticationOptions: ['None', 'Basic'],
      newRemoteInstallationUsername: null as string | null,
      newRemoteInstallationPassword: null as string | null,
      newRemoteInstallationApiToken: null as string | null,
      activeRemoteInstallationUuid: '',
    }
  },
  methods: {
    validatePublicAddress(val: string | null): boolean {
      if (!val) return true
      return val.toLowerCase().startsWith('http')
    },
    fetchSettings: function () {
      // Fetch current settings
      axios({
        method: 'get',
        url: getCompressoApiUrl('v2', 'settings/read'),
      })
        .then((response) => {
          // Set the installation name
          this.installationName = response.data.settings.installation_name
          this.installationPublicAddress = response.data.settings.installation_public_address
          // Set the list of remote installations
          const remoteInstallationsList: RemoteInstallationView[] = []
          for (let i = 0; i < response.data.settings.remote_installations.length; i++) {
            const remoteInstallation = response.data.settings.remote_installations[i]
            remoteInstallationsList.push({
              address: remoteInstallation.address,
              enableReceivingTasks: remoteInstallation.enable_receiving_tasks,
              enableSendingTasks: remoteInstallation.enable_sending_tasks,
              enableTaskPreloading: remoteInstallation.enable_task_preloading,
              enableChecksumValidation: remoteInstallation.enable_checksum_validation,
              enableConfigMissingLibraries: remoteInstallation.enable_config_missing_libraries,
              enableDistributedWorkers: remoteInstallation.enable_distributed_worker_count,
              name: remoteInstallation.name,
              version: remoteInstallation.version,
              uuid: remoteInstallation.uuid,
              available: remoteInstallation.available,
            })
          }
          this.remoteInstallations = remoteInstallationsList
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('notifications.failedToFetchSettings'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    save: function () {
      if (!this.validatePublicAddress(this.installationPublicAddress)) {
        this.$q.notify({
          color: 'negative',
          position: 'top',
          message: this.$t('components.settings.link.invalidPublicAddress'),
          icon: 'report_problem',
        })
        return
      }

      // Save settings
      const remoteInstallationsList: Array<Record<string, unknown>> = []
      for (let i = 0; i < this.remoteInstallations.length; i++) {
        const installation = this.remoteInstallations[i]
        if (!installation) continue
        remoteInstallationsList.push({
          address: installation.address,
          enable_receiving_tasks: installation.enableReceivingTasks,
          enable_sending_tasks: installation.enableSendingTasks,
          name: installation.name,
          version: installation.version,
          uuid: installation.uuid,
          available: installation.available,
        })
      }
      let data = {
        settings: {
          installation_name: this.installationName,
          installation_public_address: this.installationPublicAddress,
        },
      }
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'settings/write'),
        data: data,
      })
        .then(() => {
          // Save success, show feedback
          this.fetchSettings()
          this.$q.notify({
            color: 'positive',
            position: 'top',
            icon: 'cloud_done',
            message: this.$t('notifications.saved'),
            timeout: 200,
          })

          // Force reload of session to register the name change
          axios({
            method: 'post',
            url: getCompressoApiUrl('v2', 'session/reload'),
          }).catch((err) => {
            log.error('Failed to reload session: ' + err)
          })
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('notifications.failedToSaveSettings'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    addNewRemoteInstallation: function () {
      // Ensure this remote installation is not already in the list
      for (let i = 0; i < this.remoteInstallations.length; i++) {
        if (this.newRemoteInstallationAddress === this.remoteInstallations[i]?.address) {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('notifications.remoteInstallationAlreadyInList'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
          return
        }
      }

      // Validate connection to the provided address and add to list
      let data = {
        address: this.newRemoteInstallationAddress,
        auth: this.newRemoteInstallationAuthenticationType,
        username: this.newRemoteInstallationUsername,
        password: this.newRemoteInstallationPassword,
        api_token: this.newRemoteInstallationApiToken,
      }
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'settings/link/validate'),
        data: data,
      })
        .then((response) => {
          // Ensure this remote installation was compatible with linking
          if (typeof response.data.installation.settings.installation_name === 'undefined') {
            this.$q.notify({
              color: 'negative',
              position: 'top',
              message: this.$t('notifications.incompatibleRemoteInstallation'),
              icon: 'report_problem',
              actions: [{ icon: 'close', color: 'white' }],
            })
          } else {
            // Get name and version from API validation
            let name = response.data.installation.settings.installation_name
            let version = response.data.installation.version
            let uuid = response.data.installation.session.uuid
            // Add to list
            this.remoteInstallations.push({
              address: this.newRemoteInstallationAddress,
              auth: this.newRemoteInstallationAuthenticationType,
              username: this.newRemoteInstallationUsername,
              password: this.newRemoteInstallationPassword,
              api_token: this.newRemoteInstallationApiToken,
              enableReceivingTasks: false,
              enableSendingTasks: false,
              enableTaskPreloading: false,
              enableChecksumValidation: false,
              enableConfigMissingLibraries: false,
              enableDistributedWorkers: false,
              name: name,
              version: version,
              uuid: uuid,
              available: true,
            })
            // Trigger a save event
            let data = {
              link_config: {
                uuid: uuid,
                name: name,
                version: version,
                available: true,
                address: this.newRemoteInstallationAddress,
                auth: this.newRemoteInstallationAuthenticationType,
                username: this.newRemoteInstallationUsername,
                password: this.newRemoteInstallationPassword,
                api_token: this.newRemoteInstallationApiToken,
                enable_receiving_tasks: false,
                enable_sending_tasks: false,
              },
            }
            axios({
              method: 'post',
              url: getCompressoApiUrl('v2', 'settings/link/write'),
              data: data,
            })
              .then(() => {
                // Save success, show feedback
                this.$q.notify({
                  color: 'positive',
                  position: 'top',
                  icon: 'cloud_done',
                  message: this.$t('notifications.saved'),
                  timeout: 200,
                })
                // Close dialog
                this.addRemoteDialogRef?.hide()
              })
              .catch(() => {
                this.$q.notify({
                  color: 'negative',
                  position: 'top',
                  message: this.$t('notifications.failedToSaveSettings'),
                  icon: 'report_problem',
                  actions: [{ icon: 'close', color: 'white' }],
                })
              })
          }
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('notifications.invalidRemoteInstallationAddress'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    deleteRemoteInstallation: function (index: number) {
      const newList: RemoteInstallationView[] = []
      for (let i = 0; i < this.remoteInstallations.length; i++) {
        if (i === index) {
          // Request a DELETE from server
          const installation = this.remoteInstallations[i]
          if (!installation) continue
          let data = {
            uuid: installation.uuid,
          }
          axios({
            method: 'delete',
            url: getCompressoApiUrl('v2', 'settings/link/remove'),
            data: data,
          })
            .then(() => {
              // Save success, show feedback
              this.$q.notify({
                color: 'positive',
                position: 'top',
                icon: 'cloud_done',
                message: this.$t('notifications.saved'),
                timeout: 200,
              })
              // Update list
              //this.fetchLibraryList();
            })
            .catch(() => {
              this.$q.notify({
                color: 'negative',
                position: 'top',
                message: this.$t('notifications.failedToSaveSettings'),
                icon: 'report_problem',
                actions: [{ icon: 'close', color: 'white' }],
              })
            })
          // Remove item from the list by skipping it this loop
          continue
        }
        const installation = this.remoteInstallations[i]
        if (installation) newList.push(installation)
      }
      this.remoteInstallations = newList
    },
    configureRemoteInstallation: function (index: number) {
      const installation = this.remoteInstallations[index]
      if (!installation) return
      this.activeRemoteInstallationUuid = installation.uuid
      this.$nextTick(() => {
        if (this.$refs.remoteInstallDialogRef) {
          ;(this.$refs.remoteInstallDialogRef as DialogController).show()
        }
      })
    },
    openNewRemoteInstallationDialog: function () {
      this.addRemoteDialogRef?.show()
    },
    onRemoteInstallSaved: function () {
      this.fetchSettings()
    },
    onRemoteInstallHide: function () {
      this.activeRemoteInstallationUuid = ''
    },
  },
  created() {
    this.fetchSettings()
  },
  computed: {
    addRemoteDialogActions() {
      return [
        {
          label: this.$t('components.settings.link.add'),
          icon: 'add',
          color: 'positive',
          emit: 'add',
        },
      ]
    },
    dragOptions() {
      return {
        animation: 100,
        group: 'scheduleOrder',
        disabled: false,
        ghostClass: 'ghost',
        direction: 'vertical',
        delay: 200,
        delayOnTouchOnly: true,
      }
    },
  },
}
</script>
<style>
.page-with-mobile-quick-nav {
  padding-bottom: 24px;
}

@media (max-width: 1023px) {
  .page-with-mobile-quick-nav {
    padding-bottom: 96px;
  }
}

.ghost {
  opacity: 0;
}

div.sub-setting {
  margin-left: 30px;
  padding-top: 8px;
  padding-left: 8px;
  border-left: solid thin var(--q-primary);
}
</style>
