import { reactive } from 'vue'
import axios from 'axios'
import { getCompressoApiUrl } from './compressoGlobals'
import { createLogger } from 'src/composables/useLogger'

const log = createLogger('SharedLinks')

export const sharedLinksStore = reactive({
  target: localStorage.getItem('compresso-installation-target') || 'local',
  availableLinks: [],
  localName: '',

  async fetchLinks() {
    try {
      const response = await axios.get(getCompressoApiUrl('v2', 'settings/read'), { skipProxy: true })
      this.availableLinks = response.data.settings.remote_installations || []
      this.localName = response.data.settings.installation_name || ''
    } catch (e) {
      log.error("Failed to fetch shared links", e)
      this.availableLinks = []
    }
  },

  setTarget(newTarget) {
    this.target = newTarget
    localStorage.setItem('compresso-installation-target', newTarget)

    location.reload()
  }
})
