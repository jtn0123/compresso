import { reactive } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from './compressoGlobals'
import { createLogger } from 'src/composables/useLogger'
import type { RemoteInstallationLink } from 'src/types/contracts'

const log = createLogger('SharedLinks')

export const sharedLinksStore = reactive({
  target: localStorage.getItem('compresso-installation-target') || 'local',
  availableLinks: [] as RemoteInstallationLink[],
  localName: '',

  async fetchLinks() {
    try {
      const response = await axios.get<{
        settings: { remote_installations?: RemoteInstallationLink[]; installation_name?: string }
      }>(getCompressoApiUrl('v2', 'settings/read'), { skipProxy: true })
      this.availableLinks = response.data.settings.remote_installations ?? []
      this.localName = response.data.settings.installation_name ?? ''
    } catch (e) {
      log.error('Failed to fetch shared links', e)
      this.availableLinks = []
    }
  },

  setTarget(newTarget: string) {
    this.target = newTarget
    localStorage.setItem('compresso-installation-target', newTarget)

    location.reload()
  },
})
