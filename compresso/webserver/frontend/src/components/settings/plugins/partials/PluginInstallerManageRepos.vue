<template>
  <component
    :is="$q.screen.lt.md ? 'div' : 'q-btn-group'"
    :class="$q.screen.lt.md ? 'column q-gutter-xs full-width' : ''"
  >
    <CompressoStandardButton
      @click="reloadAllReposData()"
      v-if="$q.screen.lt.md"
      class="full-width"
      :label="$t('components.plugins.refreshRepositories')"
    />

    <CompressoStandardButton
      @click="reloadAllReposData()"
      v-if="!$q.screen.lt.md"
      :label="$t('components.plugins.refreshRepositories')"
    />

    <CompressoStandardButtonDropdown
      :label="$t('components.plugins.addRepository')"
      :class="$q.screen.lt.md ? 'full-width' : ''"
    >
      <div>
        <!--REPO DATA-->
        <div class="row no-wrap q-pa-md">
          <div class="column" :style="$q.screen.lt.md ? 'width: 100%' : 'min-width:400px'">
            <q-btn
              color="secondary"
              icon="travel_explore"
              :label="$t('components.plugins.browseCommunityRepos')"
              class="q-mb-md"
              @click="openCommunityDialog"
            />

            <q-separator class="q-mb-md" />

            <q-input filled type="textarea" v-model="newRepo" :label="$t('components.plugins.newRepository')" />

            <q-btn color="secondary" @click="saveNewRepo()" :label="$t('navigation.save')" />
          </div>
        </div>
      </div>
    </CompressoStandardButtonDropdown>

    <CompressoStandardButtonDropdown
      auto-close
      :label="$t('components.plugins.repoList')"
      :class="$q.screen.lt.md ? 'full-width' : ''"
      :fit="$q.screen.lt.md"
    >
      <div v-for="repo in repoList" :key="repo.id">
        <!-- Mobile View (lt-md) -->
        <div class="lt-md q-pa-sm">
          <q-item class="q-pa-none">
            <q-item-section avatar>
              <q-skeleton v-if="!repo.icon" type="QAvatar" />
              <q-avatar v-else rounded>
                <img :src="repo.icon" :alt="$t('a11y.repoIconAlt', { name: repo.name })" />
              </q-avatar>
            </q-item-section>

            <q-item-section style="overflow: hidden">
              <q-item-label class="text-weight-bold">{{ repo.name }}</q-item-label>
              <q-item-label caption class="ellipsis" style="max-width: 200px">
                <a
                  class="repo-link"
                  :href="getRepoDisplayUrl(repo)"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click.prevent="goToRepoSource(getRepoDisplayUrl(repo))"
                >
                  {{ getRepoDisplayUrl(repo) }}
                </a>
              </q-item-label>
            </q-item-section>

            <q-item-section side>
              <q-btn color="negative" icon="delete" outline round dense @click="removeRepo(repo.path)">
                <q-tooltip>{{ $t('tooltips.remove') }}</q-tooltip>
              </q-btn>
            </q-item-section>
          </q-item>
          <q-separator class="q-mt-sm" />
        </div>

        <!-- Desktop View (gt-sm) -->
        <div class="gt-sm row no-wrap q-pa-md">
          <div class="column repo-info">
            <div class="text-h6 q-mb-md">{{ $t('headers.information') }}:</div>

            <q-list>
              <q-item>
                <q-item-section>
                  <q-item-label>{{ $t('components.plugins.repoName') }}</q-item-label>
                  <q-item-label caption>{{ repo.name }}</q-item-label>
                </q-item-section>
              </q-item>
              <q-item>
                <q-item-section>
                  <q-item-label>{{ $t('components.plugins.repoSource') }}</q-item-label>
                  <q-item-label caption>
                    <a
                      class="repo-link"
                      :href="getRepoDisplayUrl(repo)"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.prevent="goToRepoSource(getRepoDisplayUrl(repo))"
                    >
                      {{ getRepoDisplayUrl(repo) }}
                    </a>
                  </q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </div>

          <q-separator vertical inset class="q-mx-lg" />

          <div class="column items-center">
            <q-skeleton v-if="!repo.icon" width="72px" height="72px" />
            <q-avatar v-else rounded size="72px">
              <img :src="repo.icon" :alt="$t('a11y.repoIconAlt', { name: repo.name })" />
            </q-avatar>

            <q-btn
              outline
              icon="delete"
              class="q-ma-xs"
              color="negative"
              :label="$t('tooltips.remove')"
              size="sm"
              @click="removeRepo(repo.path)"
            />
          </div>
        </div>
      </div>
    </CompressoStandardButtonDropdown>

    <CommunityRepos ref="communityRepos" @add-repo="saveNewRepo" />
  </component>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { openURL } from 'quasar'
import CommunityRepos from 'components/settings/plugins/CommunityRepos.vue'
import CompressoStandardButton from 'components/ui/buttons/CompressoStandardButton.vue'
import CompressoStandardButtonDropdown from 'components/ui/buttons/CompressoStandardButtonDropdown.vue'
import type { ApiSchema } from 'src/types/contracts'
import type { PluginRepo } from 'src/types/plugins'
import type { DialogController } from 'src/types/ui'

export default defineComponent({
  components: { CommunityRepos, CompressoStandardButton, CompressoStandardButtonDropdown },
  data() {
    return {
      repoList: [] as PluginRepo[],
      newRepo: '',
    }
  },
  methods: {
    goToRepoSource: function (url: string): void {
      openURL(url)
    },
    getRepoInfo: function () {
      // Fetch from server
      axios<ApiSchema<'PluginReposListResults'>>({
        method: 'get',
        url: getCompressoApiUrl('v2', 'plugins/repos/list'),
      })
        .then((response) => {
          // Set returned data from server results
          this.repoList = response.data.repos
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('components.plugins.failedToFetchRepos'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    updateRepoList: function (updatedReposList: string[]) {
      // POST that list to the API
      const data: ApiSchema<'RequestUpdatePluginReposList'> = {
        repos_list: updatedReposList,
      }
      return axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'plugins/repos/update'),
        data: data,
      })
    },
    reloadAllReposData: function () {
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'plugins/repos/reload'),
      })
        .then(() => {
          // Notify success
          this.$q.notify({
            color: 'positive',
            position: 'top',
            message: this.$t('notifications.reposRefreshSuccess'),
            icon: 'check_circle',
            actions: [{ icon: 'close', color: 'white' }],
          })

          // Reload the listed plugins
          this.getRepoInfo()

          // Emit a reload event due to repo update
          this.$emit('repoReloaded')
        })
        .catch(() => {
          this.$q.notify({
            color: 'warning',
            position: 'top',
            message: this.$t('notifications.reposRefreshFailure'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    saveNewRepo: function (repoUrl?: string): void {
      const urlToAdd = typeof repoUrl === 'string' ? repoUrl : this.newRepo

      if (urlToAdd.length > 0) {
        const updatedReposList: string[] = []

        // Check if urlToAdd already exists in repo list
        for (let i = 0; i < this.repoList.length; i++) {
          const repoPath = this.repoList[i]?.path
          if (!repoPath) continue
          if (urlToAdd.trim() === repoPath) {
            this.$q.notify({
              color: 'negative',
              position: 'top',
              message: this.$t('notifications.repoAlreadyExists') + ' "' + urlToAdd.trim() + '"',
              icon: 'report_problem',
              actions: [{ icon: 'close', color: 'white' }],
            })
            return
          } else {
            // Add this current repo path to new list
            updatedReposList[updatedReposList.length] = repoPath
          }
        }
        // Repo does not yet exist...
        // Add new repo to current repo list
        updatedReposList[updatedReposList.length] = urlToAdd.trim()

        // POST that list to the API
        this.updateRepoList(updatedReposList)
          .then(() => {
            // Notify save
            this.$q.notify({
              color: 'positive',
              position: 'top',
              message: this.$t('notifications.saved'),
              icon: 'cloud_done',
              actions: [{ icon: 'close', color: 'white' }],
            })

            // Remove value from input field if it was used
            if (!repoUrl) {
              this.newRepo = ''
            }

            // Reload all repos
            this.reloadAllReposData()

            // Emit a reload event due to repo update
            this.$emit('repoReloaded', true)
          })
          .catch(() => {
            this.$q.notify({
              color: 'negative',
              position: 'top',
              message: this.$t('notifications.newRepoAddFailed'),
              icon: 'report_problem',
              actions: [{ icon: 'close', color: 'white' }],
            })
          })
      }
    },
    getRepoDisplayUrl: function (repo: PluginRepo): string {
      if (repo.repo_html_url) {
        return repo.repo_html_url
      }
      if (repo.path && repo.path.startsWith('http')) {
        return repo.path
      }
      return ''
    },
    removeRepo: function (repoPath: string): void {
      const updatedReposList: string[] = []

      // Check if repoPath actually exists in repo list
      // Create updatedReposList from all other paths but the one we want removed
      for (let i = 0; i < this.repoList.length; i++) {
        const repo = this.repoList[i]
        if (!repo) continue
        if (repoPath.trim() !== repo.path) {
          updatedReposList[updatedReposList.length] = repo.path
        }
      }

      // POST the updated repo list to the API
      this.updateRepoList(updatedReposList)
        .then(() => {
          // Notify save
          this.$q.notify({
            color: 'positive',
            position: 'top',
            message: this.$t('notifications.repoRemovedSuccess') + ' "' + repoPath.trim() + '"',
            icon: 'check_circle',
            actions: [{ icon: 'close', color: 'white' }],
          })

          // Reload all repos
          this.reloadAllReposData()

          // Emit a reload event due to repo update
          this.$emit('repoReloaded')
        })
        .catch(() => {
          this.$q.notify({
            color: 'negative',
            position: 'top',
            message: this.$t('notifications.repoRemovedFailed'),
            icon: 'report_problem',
            actions: [{ icon: 'close', color: 'white' }],
          })
        })
    },
    openCommunityDialog() {
      ;(this.$refs.communityRepos as DialogController).show()
    },
  },
  created() {
    this.getRepoInfo()
  },
  emits: {
    repoReloaded: (_reloaded?: boolean) => true,
  },
})
</script>

<style scoped>
.repo-info {
  flex: 1;
  min-width: 0;
}

.repo-link {
  color: var(--q-primary);
  text-decoration: underline;
  text-underline-offset: 0.2em;
}

.repo-link:focus-visible {
  outline: 3px solid var(--q-secondary);
  outline-offset: 3px;
  border-radius: 2px;
}
</style>
