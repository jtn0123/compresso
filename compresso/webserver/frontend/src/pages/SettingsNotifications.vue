<template>
  <q-page padding class="page-with-mobile-quick-nav">
    <div class="q-pa-none">
      <div class="row">
        <div class="col-sm-12 col-md-10 col-lg-8">
          <div :class="$q.platform.is.mobile ? 'q-ma-sm' : 'q-ma-sm q-pa-md'">
            <PageHeader
              :title="$t('pages.settingsNotifications.title')"
              :subtitle="$t('pages.settingsNotifications.subtitle')"
            />

            <!-- Channel List -->
            <q-card flat bordered class="q-mb-md q-mt-lg">
              <q-card-section>
                <div class="text-subtitle1 text-weight-bold">
                  {{ $t('pages.settingsNotifications.configuredChannels') }}
                </div>
              </q-card-section>

              <!-- Loading state -->
              <q-card-section v-if="loading">
                <q-skeleton type="QInput" class="q-mb-sm" />
                <q-skeleton type="QInput" />
              </q-card-section>

              <!-- Empty state when no channels -->
              <q-card-section v-else-if="channels.length === 0">
                <div class="text-grey text-center q-pa-lg">
                  {{ $t('pages.settingsNotifications.noChannels') }}
                </div>
              </q-card-section>

              <!-- Channel list items -->
              <q-list separator v-else>
                <q-item v-for="channel in channels" :key="channel.id">
                  <q-item-section avatar>
                    <q-icon :name="channelIcon(channel.type)" :color="channelColor(channel.type)" />
                  </q-item-section>
                  <q-item-section>
                    <q-item-label>{{ channel.name }}</q-item-label>
                    <q-item-label caption>
                      <q-badge
                        :color="channelColor(channel.type)"
                        :label="channelTypeLabel(channel.type)"
                        class="q-mr-xs"
                      />
                      <span class="text-grey"
                        >{{ channel.triggers.length }} {{ $t('pages.settingsNotifications.triggerCount') }}</span
                      >
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <div class="row items-center q-gutter-xs">
                      <q-toggle v-model="channel.enabled" @update:model-value="saveChannels" dense />
                      <q-btn
                        flat
                        dense
                        icon="send"
                        size="sm"
                        @click="testChannel(channel)"
                        :loading="testingId === channel.id"
                      >
                        <q-tooltip>{{ $t('pages.settingsNotifications.sendTest') }}</q-tooltip>
                      </q-btn>
                      <q-btn flat dense icon="edit" size="sm" @click="editChannel(channel)">
                        <q-tooltip>{{ $t('tooltips.configure') }}</q-tooltip>
                      </q-btn>
                      <q-btn flat dense icon="delete" color="negative" size="sm" @click="confirmDelete(channel)">
                        <q-tooltip>{{ $t('tooltips.delete') }}</q-tooltip>
                      </q-btn>
                    </div>
                  </q-item-section>
                </q-item>
              </q-list>

              <q-card-actions>
                <q-btn
                  color="primary"
                  icon="add"
                  :label="$t('pages.settingsNotifications.addChannel')"
                  @click="openAddDialog"
                />
              </q-card-actions>
            </q-card>

            <!-- Add/Edit Dialog -->
            <q-dialog v-model="showDialog" persistent>
              <q-card style="min-width: 500px">
                <q-card-section>
                  <div class="text-h6">
                    {{
                      editingChannel
                        ? $t('pages.settingsNotifications.editChannel')
                        : $t('pages.settingsNotifications.addChannel')
                    }}
                  </div>
                </q-card-section>
                <q-card-section>
                  <q-form @submit.prevent="saveDialog" class="q-gutter-md">
                    <q-input
                      outlined
                      v-model="dialogForm.name"
                      :label="$t('pages.settingsNotifications.channelName')"
                      :rules="[(v) => !!v || $t('pages.settingsNotifications.fieldRequired')]"
                    />
                    <q-select
                      outlined
                      v-model="dialogForm.type"
                      :options="typeOptions"
                      :label="$t('pages.settingsNotifications.channelType')"
                      emit-value
                      map-options
                      :rules="[(v) => !!v || $t('pages.settingsNotifications.fieldRequired')]"
                    />
                    <q-input
                      outlined
                      v-model="dialogForm.url"
                      :label="$t('pages.settingsNotifications.webhookUrl')"
                      type="url"
                      :rules="[(v) => !!v || $t('pages.settingsNotifications.fieldRequired')]"
                      :hint="urlHint"
                    />
                    <q-input
                      v-if="dialogForm.type === 'webhook'"
                      outlined
                      v-model="dialogForm.headersRaw"
                      :label="$t('pages.settingsNotifications.customHeaders')"
                      type="textarea"
                      rows="2"
                      :hint="$t('pages.settingsNotifications.customHeadersHint')"
                    />

                    <div class="text-subtitle2 q-mt-md">
                      {{ $t('pages.settingsNotifications.triggerEvents') }}
                    </div>
                    <div class="q-gutter-sm">
                      <q-checkbox
                        v-for="trigger in triggerOptions"
                        :key="trigger.value"
                        v-model="dialogForm.triggers"
                        :val="trigger.value"
                        :label="trigger.label"
                      />
                    </div>
                  </q-form>
                </q-card-section>
                <q-card-actions align="right">
                  <q-btn flat :label="$t('navigation.cancel')" v-close-popup />
                  <q-btn
                    color="primary"
                    :label="editingChannel ? $t('navigation.save') : $t('pages.settingsNotifications.addChannel')"
                    @click="saveDialog"
                  />
                </q-card-actions>
              </q-card>
            </q-dialog>
          </div>
        </div>
      </div>

      <MobileSettingsQuickNav
        :prev-enabled="true"
        :prev-label="$t('navigation.link')"
        :prev-path="'/ui/settings-link'"
        :next-enabled="false"
        :next-label="'none'"
        :next-path="'/ui/settings-link'"
      />
    </div>
  </q-page>
</template>

<script>
import { CompressoWebsocketHandler } from 'src/js/compressoWebsocket'
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import MobileSettingsQuickNav from 'components/MobileSettingsQuickNav'
import PageHeader from 'components/ui/PageHeader.vue'

export default {
  name: 'SettingsNotifications',
  components: {
    MobileSettingsQuickNav,
    PageHeader,
  },
  setup() {
    const { t: $t } = useI18n()

    let ws = null
    let compressoWSHandler = CompressoWebsocketHandler($t)

    function initCompressoWebsocket() {
      ws = compressoWSHandler.init()
    }

    function closeCompressoWebsocket() {
      compressoWSHandler.close()
    }

    onMounted(() => {
      initCompressoWebsocket()
    })
    onUnmounted(() => {
      closeCompressoWebsocket()
    })

    return {}
  },
  data() {
    return {
      loading: ref(true),
      channels: ref([]),
      showDialog: ref(false),
      editingChannel: ref(null),
      testingId: ref(null),
      dialogForm: ref({
        name: '',
        type: '',
        url: '',
        headersRaw: '',
        triggers: [],
      }),
    }
  },
  computed: {
    typeOptions() {
      return [
        { label: 'Discord', value: 'discord' },
        { label: 'Slack', value: 'slack' },
        { label: this.$t('pages.settingsNotifications.typeWebhook'), value: 'webhook' },
      ]
    },
    triggerOptions() {
      return [
        { label: this.$t('pages.settingsNotifications.triggers.taskCompleted'), value: 'task_completed' },
        { label: this.$t('pages.settingsNotifications.triggers.taskFailed'), value: 'task_failed' },
        { label: this.$t('pages.settingsNotifications.triggers.queueEmpty'), value: 'queue_empty' },
        { label: this.$t('pages.settingsNotifications.triggers.approvalNeeded'), value: 'approval_needed' },
        { label: this.$t('pages.settingsNotifications.triggers.healthCheckFailed'), value: 'health_check_failed' },
      ]
    },
    urlHint() {
      if (this.dialogForm.type === 'discord') {
        return this.$t('pages.settingsNotifications.hintDiscord')
      }
      if (this.dialogForm.type === 'slack') {
        return this.$t('pages.settingsNotifications.hintSlack')
      }
      return this.$t('pages.settingsNotifications.hintWebhook')
    },
  },
  methods: {
    channelIcon(type) {
      const icons = {
        discord: 'fab fa-discord',
        slack: 'fab fa-slack',
        webhook: 'webhook',
      }
      return icons[type] || 'webhook'
    },
    channelColor(type) {
      const colors = {
        discord: 'indigo',
        slack: 'green',
        webhook: 'grey',
      }
      return colors[type] || 'grey'
    },
    channelTypeLabel(type) {
      const labels = {
        discord: 'Discord',
        slack: 'Slack',
        webhook: this.$t('pages.settingsNotifications.typeWebhook'),
      }
      return labels[type] || type
    },
    generateId() {
      if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID()
      }
      // Fallback for older browsers
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0
        const v = c === 'x' ? r : (r & 0x3) | 0x8
        return v.toString(16)
      })
    },
    fetchChannels() {
      this.loading = true
      axios({
        method: 'get',
        url: getCompressoApiUrl('v2', 'notifications/channels'),
      })
        .then((response) => {
          this.channels = response.data.channels || []
          this.loading = false
        })
        .catch(() => {
          this.channels = []
          this.loading = false
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('pages.settingsNotifications.fetchError'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    saveChannels() {
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'notifications/channels/save'),
        data: { channels: this.channels },
      })
        .then(() => {
          this.$q.notify({
            color: 'positive',
            position: 'top',
            icon: 'cloud_done',
            message: this.$t('notifications.saved'),
            timeout: 200,
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
    testChannel(channel) {
      this.testingId = channel.id
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'notifications/channels/test'),
        data: { channel: channel },
      })
        .then(() => {
          this.testingId = null
          this.$q.notify({
            color: 'positive',
            position: 'top',
            icon: 'check_circle',
            message: this.$t('pages.settingsNotifications.testSuccess'),
            timeout: 3000,
          })
        })
        .catch(() => {
          this.testingId = null
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('pages.settingsNotifications.testFailed'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    openAddDialog() {
      this.editingChannel = null
      this.dialogForm = {
        name: '',
        type: '',
        url: '',
        headersRaw: '',
        triggers: [],
      }
      this.showDialog = true
    },
    editChannel(channel) {
      this.editingChannel = channel
      this.dialogForm = {
        name: channel.name,
        type: channel.type,
        url: channel.url,
        headersRaw: channel.headers ? JSON.stringify(channel.headers) : '',
        triggers: [...channel.triggers],
      }
      this.showDialog = true
    },
    saveDialog() {
      // Validate required fields
      if (!this.dialogForm.name || !this.dialogForm.type || !this.dialogForm.url) {
        return
      }

      // Parse custom headers if provided
      let headers = null
      if (this.dialogForm.type === 'webhook' && this.dialogForm.headersRaw) {
        try {
          headers = JSON.parse(this.dialogForm.headersRaw)
        } catch {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('notifications.invalidJson'),
            icon: 'report_problem',
          })
          return
        }
      }

      if (this.editingChannel) {
        // Update existing channel
        const idx = this.channels.findIndex((c) => c.id === this.editingChannel.id)
        if (idx !== -1) {
          this.channels[idx].name = this.dialogForm.name
          this.channels[idx].type = this.dialogForm.type
          this.channels[idx].url = this.dialogForm.url
          this.channels[idx].headers = headers
          this.channels[idx].triggers = [...this.dialogForm.triggers]
        }
      } else {
        // Add new channel
        this.channels.push({
          id: this.generateId(),
          name: this.dialogForm.name,
          type: this.dialogForm.type,
          url: this.dialogForm.url,
          headers: headers,
          triggers: [...this.dialogForm.triggers],
          enabled: true,
        })
      }

      this.showDialog = false
      this.saveChannels()
    },
    confirmDelete(channel) {
      this.$q
        .dialog({
          title: this.$t('headers.confirm'),
          message: this.$t('pages.settingsNotifications.confirmDelete', { name: channel.name }),
          cancel: true,
          persistent: true,
        })
        .onOk(() => {
          this.channels = this.channels.filter((c) => c.id !== channel.id)
          this.saveChannels()
        })
    },
  },
  created() {
    this.fetchChannels()
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
</style>
