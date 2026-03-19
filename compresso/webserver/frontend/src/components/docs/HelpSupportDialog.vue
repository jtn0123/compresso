<template>
  <CompressoDialogWindow
    ref="dialogRef"
    :title="$t('navigation.helpAndSupport')"
    @hide="onDialogHide"
  >
    <div class="q-pa-none">
      <!-- About Section -->
      <div class="q-pa-md q-mb-md">
        <h5 class="q-mb-sm q-mt-none">{{ $t('about.title') }}</h5>
        <p class="text-body2 q-mb-sm">{{ $t('about.description') }}</p>
        <q-list dense class="q-mb-sm">
          <q-item dense class="q-pa-none">
            <q-item-section avatar style="min-width: 24px">
              <q-icon name="check_circle" color="positive" size="16px" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="text-caption">{{ $t('about.features.approval') }}</q-item-label>
            </q-item-section>
          </q-item>
          <q-item dense class="q-pa-none">
            <q-item-section avatar style="min-width: 24px">
              <q-icon name="check_circle" color="positive" size="16px" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="text-caption">{{ $t('about.features.compression') }}</q-item-label>
            </q-item-section>
          </q-item>
          <q-item dense class="q-pa-none">
            <q-item-section avatar style="min-width: 24px">
              <q-icon name="check_circle" color="positive" size="16px" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="text-caption">{{ $t('about.features.preview') }}</q-item-label>
            </q-item-section>
          </q-item>
          <q-item dense class="q-pa-none">
            <q-item-section avatar style="min-width: 24px">
              <q-icon name="check_circle" color="positive" size="16px" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="text-caption">{{ $t('about.features.healthCheck') }}</q-item-label>
            </q-item-section>
          </q-item>
          <q-item dense class="q-pa-none">
            <q-item-section avatar style="min-width: 24px">
              <q-icon name="check_circle" color="positive" size="16px" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="text-caption">{{ $t('about.features.links') }}</q-item-label>
            </q-item-section>
          </q-item>
          <q-item dense class="q-pa-none">
            <q-item-section avatar style="min-width: 24px">
              <q-icon name="check_circle" color="positive" size="16px" />
            </q-item-section>
            <q-item-section>
              <q-item-label class="text-caption">{{ $t('about.features.plugins') }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
        <div class="row items-center q-gutter-sm">
          <span class="text-caption text-grey" v-if="appVersion">{{ $t('components.settings.support.appVersion') }}: {{ appVersion }}</span>
          <q-btn
            flat
            dense
            size="sm"
            icon="fab fa-github"
            :label="$t('about.githubLink')"
            @click="openExternalURL($t('about.githubUrl'))"
          />
        </div>
      </div>
      <q-separator class="q-mb-md" />
      <div class="row">
        <div class="col q-ma-sm">
          <div class="row">
            <div class="col-sm-7 col-xs-12">
              <!--START CONFIGURATION-->
              <h5 class="q-mb-none q-mt-sm q-pl-sm">{{ $t('components.settings.support.configuration') }}</h5>
              <div class="q-gutter-sm">
                <q-skeleton
                  v-if="debugging === null"
                  type="QToggle"/>
                <div class="q-pa-md" style="max-width: 560px">
                  <q-list
                    padding
                    class="rounded-borders">

                    <q-item>
                      <q-item-section avatar>
                        <q-img src="~assets/compresso-logo-white.png"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.appVersion') }}:</q-item-label>
                        <q-item-label caption>{{ appVersion }}</q-item-label>
                      </q-item-section>
                    </q-item>
                    <q-separator spaced inset="item"/>
                    <q-item>
                      <q-item-section avatar>
                        <q-icon color="primary" name="fab fa-python"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.pythonVersion') }}:</q-item-label>
                        <q-item-label caption>{{ pythonVersion }}</q-item-label>
                      </q-item-section>
                    </q-item>
                    <q-separator spaced inset="item"/>
                    <q-item>
                      <q-item-section avatar>
                        <q-icon color="primary" name="computer"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.platform') }}:</q-item-label>
                        <q-item-label caption>{{ platform }}</q-item-label>
                      </q-item-section>
                    </q-item>
                    <q-separator spaced inset="item"/>
                    <q-item>
                      <q-item-section avatar>
                        <q-icon color="primary" name="fas fa-folder"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.configPath') }}:</q-item-label>
                        <q-item-label caption>{{ configPath }}</q-item-label>
                      </q-item-section>
                    </q-item>
                    <q-item>
                      <q-item-section avatar>
                        <q-icon color="primary" name="fas fa-folder"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.logsPath') }}:</q-item-label>
                        <q-item-label caption>{{ logsPath }}</q-item-label>
                      </q-item-section>
                    </q-item>
                    <q-item>
                      <q-item-section avatar>
                        <q-icon color="primary" name="fas fa-folder"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.userdataPath') }}:</q-item-label>
                        <q-item-label caption>{{ userdataPath }}</q-item-label>
                      </q-item-section>
                    </q-item>

                  </q-list>
                </div>
              </div>
              <!--END CONFIGURATION-->
            </div>
            <div class="col-sm-5 col-xs-12">
              <!--START EXT DOC LINKS-->
              <h5 class="q-mb-none q-mt-sm">{{ $t('components.settings.support.docs') }}</h5>
              <div class="q-gutter-sm">
                <q-skeleton
                  v-if="debugging === null"
                  type="QToggle"/>
                <div class="q-pa-md" style="max-width: 550px">
                  <q-list
                    dense
                    class="q-pl-sm">
                    <q-item clickable dense class="support-link-row rounded-borders"
                            @click="openExternalURL('/compresso/swagger')">
                      <q-item-section avatar>
                        <q-icon color="primary" name="article" size="18px"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.apiSpec') }}</q-item-label>
                      </q-item-section>
                      <q-item-section side>
                        <q-icon color="secondary" name="open_in_new" size="16px"/>
                      </q-item-section>
                    </q-item>
                    <q-item clickable dense class="support-link-row rounded-borders"
                            @click="openExternalURL('https://github.com/jtn0123/compresso#install-and-run')">
                      <q-item-section avatar>
                        <q-icon color="primary" name="article" size="18px"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.applicationDocumentation') }}</q-item-label>
                      </q-item-section>
                      <q-item-section side>
                        <q-icon color="secondary" name="open_in_new" size="16px"/>
                      </q-item-section>
                    </q-item>
                  </q-list>
                </div>
              </div>
              <!--END EXT DOC LINKS-->

              <!--START EXT SUPPORT LINKS-->
              <h5 class="q-mb-none q-mt-sm">{{ $t('components.settings.support.support') }}</h5>
              <div class="q-gutter-sm">
                <q-skeleton
                  v-if="debugging === null"
                  type="QToggle"/>
                <div class="q-pa-md" style="max-width: 550px">
                  <q-list
                    dense
                    class="q-pl-sm">
                    <q-item clickable dense class="support-link-row rounded-borders"
                            @click="openExternalURL('https://github.com/jtn0123/compresso/issues')">
                      <q-item-section avatar>
                        <q-icon color="primary" name="fab fa-github" size="18px"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ $t('components.settings.support.compressoAppSourceRequests') }}</q-item-label>
                      </q-item-section>
                      <q-item-section side>
                        <q-icon color="secondary" name="open_in_new" size="16px"/>
                      </q-item-section>
                    </q-item>
                    <q-item clickable dense class="support-link-row rounded-borders"
                            @click="openExternalURL('https://github.com/jtn0123/compresso/issues')">
                      <q-item-section avatar>
                        <q-icon color="primary" name="fab fa-github" size="18px"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{
                            $t('components.settings.support.compressoFrontendSourceRequests')
                          }}
                        </q-item-label>
                      </q-item-section>
                      <q-item-section side>
                        <q-icon color="secondary" name="open_in_new" size="16px"/>
                      </q-item-section>
                    </q-item>
                    <q-item clickable dense class="support-link-row rounded-borders"
                            @click="openExternalURL('https://github.com/jtn0123/compresso/issues')">
                      <q-item-section avatar>
                        <q-icon color="primary" name="fab fa-github" size="18px"/>
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{
                            $t('components.settings.support.compressoOfficialPluginRequests')
                          }}
                        </q-item-label>
                      </q-item-section>
                      <q-item-section side>
                        <q-icon color="secondary" name="open_in_new" size="16px"/>
                      </q-item-section>
                    </q-item>
                  </q-list>
                </div>
              </div>
              <!--END EXT DOC LINKS-->
            </div>
          </div>



        </div>
      </div>
    </div>
  </CompressoDialogWindow>
</template>

<script>
import { ref } from "vue";
import { useQuasar } from 'quasar'
import { useI18n } from "vue-i18n";
import axios from "axios";
import compressoGlobals, { getCompressoApiUrl } from "src/js/compressoGlobals";
import { openURL } from 'quasar'
import CompressoDialogWindow from "components/ui/dialogs/CompressoDialogWindow.vue";

export default {
  name: 'HelpSupportDialog',
  components: {
    CompressoDialogWindow
  },
  emits: ['hide'],
  setup() {
    useQuasar()
    useI18n();
    const logsPath = ref('');

    const appVersion = ref(null);
    const pythonVersion = ref(null);
    const platform = ref(null);
    const configPath = ref(null);
    const userdataPath = ref(null);

    return {
      logsPath,
      appVersion,
      pythonVersion,
      platform,
      configPath,
      userdataPath,
    }
  },
  data() {
    return {
      debugging: ref(null),
    }
  },
  methods: {
    show() {
      if (this.$refs.dialogRef) {
        this.$refs.dialogRef.show();
      }
      this.fetchSettings();
      this.fetchSystemConfig();
    },
    hide() {
      if (this.$refs.dialogRef) {
        this.$refs.dialogRef.hide();
      }
    },
    onDialogHide() {
      this.$emit('hide');
    },
    openExternalURL: function (url) {
      openURL(url)
    },
    fetchSettings: function () {
      // Fetch current settings
      axios({
        method: 'get',
        url: getCompressoApiUrl('v2', 'settings/read')
      }).then((response) => {
        this.debugging = response.data.settings.debugging

        // Set system configuration paths
        this.configPath = response.data.settings.config_path;
        this.logsPath = response.data.settings.log_path;
        this.userdataPath = response.data.settings.userdata_path;

      }).catch(() => {
        this.$q.notify({
          color: 'negative',
          position: 'top',
          message: this.$t('notifications.failedToFetchSettings'),
          icon: 'report_problem',
          actions: [{ icon: 'close', color: 'white' }]
        })
      });
    },
    fetchSystemConfig: function () {
      // Fetch compresso version
      compressoGlobals.getCompressoVersion().then((version) => {
        this.appVersion = version;
      })
      // Fetch system config
      axios({
        method: 'get',
        url: getCompressoApiUrl('v2', 'settings/configuration')
      }).then((response) => {
        let configuration = response.data.configuration;

        // Set python versoin
        this.pythonVersion = configuration.python;

        // Set platform data
        if (typeof configuration.platform !== 'undefined' && configuration.platform.length > 0) {
          let platform = configuration.platform.join(' ');
          console.log(platform)
          this.platform = platform;
        }

      }).catch(() => {
        this.$q.notify({
          color: 'negative',
          position: 'top',
          message: this.$t('notifications.failedToFetchSystemConfig'),
          icon: 'report_problem',
          actions: [{ icon: 'close', color: 'white' }]
        })
      });
    },


  },
  created() {
    // Settings and system config are now fetched in show() to avoid
    // unnecessary API calls and error toasts when the dialog isn't visible
  }
}
</script>

<style lang="scss">
.support-link-row {
  min-height: 28px;
  padding: 2px 8px;
}
</style>
