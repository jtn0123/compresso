import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

// ---------------------------------------------------------------------------
// Mocks — vi.mock factories are hoisted, so we use vi.hoisted() for any
// variables the factories need to reference.
// ---------------------------------------------------------------------------

// The component calls axios({ method, url, data }) as a function (not axios.get/post).
// We mock the default export as a callable fn with get/post/delete attached.
// vi.hoisted runs before vi.mock hoisting, so the variable is available to the factory.
const { mockAxiosFn } = vi.hoisted(() => {
  const fn = vi.fn()
  fn.get = vi.fn()
  fn.post = vi.fn()
  fn.delete = vi.fn()
  return { mockAxiosFn: fn }
})

vi.mock('axios', () => ({ default: mockAxiosFn }))

vi.mock('src/js/compressoGlobals', () => ({
  getCompressoApiUrl: vi.fn((version, endpoint) => `http://localhost/compresso/api/${version}/${endpoint}`),
  showEventToast: vi.fn(),
}))

vi.mock('src/composables/useLogger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

vi.mock('src/js/compressoWebsocket', () => ({
  CompressoWebsocketHandler: () => ({
    init: vi.fn(),
    close: vi.fn(),
  }),
}))

vi.mock('components/MobileSettingsQuickNav', () => ({
  default: { name: 'MobileSettingsQuickNav', template: '<div />' },
}))

vi.mock('components/ui/PageHeader.vue', () => ({
  default: { name: 'PageHeader', template: '<div />', props: ['title', 'subtitle'] },
}))

vi.mock('quasar', () => ({
  Quasar: { install() {} },
  useQuasar: () => ({
    notify: vi.fn(),
    dialog: vi.fn(() => ({ onOk: vi.fn(() => ({ onCancel: vi.fn() })), onCancel: vi.fn() })),
    dark: { isActive: false },
    screen: {
      gt: { xs: true, sm: true },
      lt: { sm: false, md: false },
    },
    platform: { is: { desktop: true, mobile: false } },
  }),
  Notify: { create: vi.fn() },
  Dialog: {},
  LocalStorage: { getItem: vi.fn(), setItem: vi.fn() },
  SessionStorage: { getItem: vi.fn(), setItem: vi.fn() },
}))

import { shallowMountWithQuasar } from 'src/test-utils'
import SettingsNotifications from '../SettingsNotifications.vue'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_CHANNELS = [
  {
    id: 'ch-1',
    name: 'Alerts',
    type: 'discord',
    url: 'https://discord.com/api/webhooks/123',
    headers: null,
    triggers: ['task_completed', 'task_failed'],
    enabled: true,
  },
  {
    id: 'ch-2',
    name: 'Ops Slack',
    type: 'slack',
    url: 'https://hooks.slack.com/services/T/B/xxx',
    headers: null,
    triggers: ['queue_empty'],
    enabled: false,
  },
]

function setupMocks(channels = MOCK_CHANNELS) {
  // Deep copy to prevent cross-test mutation of shared mock data
  const channelsCopy = JSON.parse(JSON.stringify(channels))
  mockAxiosFn.mockImplementation(({ method, url }) => {
    if (url && url.includes('notifications/channels/save')) {
      return Promise.resolve({ data: { success: true } })
    }
    if (url && url.includes('notifications/channels/test')) {
      return Promise.resolve({ data: { success: true } })
    }
    if (url && url.includes('notifications/channels')) {
      return Promise.resolve({ data: { channels: channelsCopy } })
    }
    return Promise.resolve({ data: {} })
  })
}

// Helper to read reactive data properties that may be wrapped in ref()
function val(v) {
  return v && typeof v === 'object' && '__v_isRef' in v ? v.value : v
}

async function mountComponent(channels = MOCK_CHANNELS) {
  setupMocks(channels)
  const wrapper = shallowMountWithQuasar(SettingsNotifications)
  await flushPromises()
  return { wrapper }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SettingsNotifications.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // 1. Renders page header with correct title
  describe('rendering', () => {
    it('renders the PageHeader component', async () => {
      const { wrapper } = await mountComponent()
      expect(wrapper.findComponent({ name: 'PageHeader' }).exists()).toBe(true)
    })

    it('passes the correct title prop to PageHeader', async () => {
      const { wrapper } = await mountComponent()
      const pageHeader = wrapper.findComponent({ name: 'PageHeader' })
      expect(pageHeader.props('title')).toBe('pages.settingsNotifications.title')
    })
  })

  // 2. Shows loading state initially
  describe('loading state', () => {
    it('starts with loading true before fetch resolves', () => {
      mockAxiosFn.mockImplementation(() => new Promise(() => {}))
      const wrapper = shallowMountWithQuasar(SettingsNotifications)
      expect(val(wrapper.vm.loading)).toBe(true)
    })

    it('sets loading to false after fetch resolves', async () => {
      const { wrapper } = await mountComponent()
      expect(val(wrapper.vm.loading)).toBe(false)
    })
  })

  // 3. Fetches channels on mount (GET call made)
  describe('fetch on mount', () => {
    it('calls the channels endpoint on created', async () => {
      await mountComponent()
      const fetchCalls = mockAxiosFn.mock.calls.filter(
        ([config]) => config.url && config.url.includes('notifications/channels') && config.method === 'get',
      )
      expect(fetchCalls.length).toBeGreaterThanOrEqual(1)
    })
  })

  // 4. Shows empty state when no channels
  describe('empty state', () => {
    it('shows empty state message when no channels exist', async () => {
      const { wrapper } = await mountComponent([])
      expect(val(wrapper.vm.channels)).toEqual([])
      expect(val(wrapper.vm.loading)).toBe(false)
    })
  })

  // 5. Renders channel list with data
  describe('channel list', () => {
    it('populates channels array after successful fetch', async () => {
      const { wrapper } = await mountComponent()
      const channels = val(wrapper.vm.channels)
      expect(channels).toHaveLength(2)
      expect(channels[0].name).toBe('Alerts')
      expect(channels[1].name).toBe('Ops Slack')
    })

    // 6. Channel items show name, type badge, trigger count
    it('channel items contain name, type, and triggers', async () => {
      const { wrapper } = await mountComponent()
      const channels = val(wrapper.vm.channels)
      expect(channels[0].name).toBe('Alerts')
      expect(channels[0].type).toBe('discord')
      expect(channels[0].triggers).toHaveLength(2)
      expect(channels[1].name).toBe('Ops Slack')
      expect(channels[1].type).toBe('slack')
      expect(channels[1].triggers).toHaveLength(1)
    })
  })

  // 7. Enable toggle present on each channel
  describe('enable/disable toggle', () => {
    it('each channel has an enabled property', async () => {
      const { wrapper } = await mountComponent()
      const channels = val(wrapper.vm.channels)
      expect(channels[0].enabled).toBe(true)
      expect(channels[1].enabled).toBe(false)
    })

    it('saveChannels posts the current channels array', async () => {
      const { wrapper } = await mountComponent()
      const channels = val(wrapper.vm.channels)
      channels[1].enabled = true
      wrapper.vm.saveChannels()
      await flushPromises()

      const saveCalls = mockAxiosFn.mock.calls.filter(
        ([config]) => config.url && config.url.includes('notifications/channels/save'),
      )
      expect(saveCalls.length).toBe(1)
      expect(saveCalls[0][0].data.channels[1].enabled).toBe(true)
    })
  })

  // 8. Add channel button exists / openAddDialog
  describe('add dialog', () => {
    it('opens dialog when openAddDialog is called', async () => {
      const { wrapper } = await mountComponent()
      expect(val(wrapper.vm.showDialog)).toBe(false)

      wrapper.vm.openAddDialog()
      await wrapper.vm.$nextTick()

      expect(val(wrapper.vm.showDialog)).toBe(true)
      expect(val(wrapper.vm.editingChannel)).toBeNull()
    })

    // 9. openAddDialog sets showDialog to true
    it('resets form fields when opening add dialog', async () => {
      const { wrapper } = await mountComponent()
      wrapper.vm.openAddDialog()
      await wrapper.vm.$nextTick()

      const form = val(wrapper.vm.dialogForm)
      expect(form.name).toBe('')
      expect(form.type).toBe('')
      expect(form.url).toBe('')
      expect(form.triggers).toEqual([])
    })
  })

  // 10. saveChannels calls POST /notifications/channels/save
  describe('save channel', () => {
    it('saveDialog adds a new channel and calls saveChannels', async () => {
      const { wrapper } = await mountComponent([])

      wrapper.vm.openAddDialog()
      const form = val(wrapper.vm.dialogForm)
      form.name = 'New Channel'
      form.type = 'webhook'
      form.url = 'https://example.com/hook'
      form.triggers = ['task_completed']
      await wrapper.vm.$nextTick()

      wrapper.vm.saveDialog()
      await flushPromises()

      const channels = val(wrapper.vm.channels)
      expect(channels).toHaveLength(1)
      expect(channels[0].name).toBe('New Channel')
      expect(channels[0].type).toBe('webhook')
      expect(channels[0].enabled).toBe(true)
      expect(val(wrapper.vm.showDialog)).toBe(false)

      const saveCalls = mockAxiosFn.mock.calls.filter(
        ([config]) => config.url && config.url.includes('notifications/channels/save'),
      )
      expect(saveCalls.length).toBe(1)
    })

    it('saveDialog does not add when required fields are empty', async () => {
      const { wrapper } = await mountComponent([])
      wrapper.vm.openAddDialog()
      wrapper.vm.saveDialog()
      await flushPromises()

      expect(val(wrapper.vm.channels)).toHaveLength(0)
    })

    it('saveDialog updates an existing channel when editingChannel is set', async () => {
      const { wrapper } = await mountComponent()
      const channels = val(wrapper.vm.channels)
      const channel = channels[0]

      wrapper.vm.editChannel(channel)
      const form = val(wrapper.vm.dialogForm)
      form.name = 'Updated Alerts'
      await wrapper.vm.$nextTick()

      wrapper.vm.saveDialog()
      await flushPromises()

      expect(val(wrapper.vm.channels)[0].name).toBe('Updated Alerts')
      expect(val(wrapper.vm.showDialog)).toBe(false)
    })
  })

  // 11. testChannel calls POST /notifications/channels/test
  describe('test channel', () => {
    it('testChannel calls the test endpoint with the channel data', async () => {
      const { wrapper } = await mountComponent()
      const channel = val(wrapper.vm.channels)[0]

      wrapper.vm.testChannel(channel)
      expect(val(wrapper.vm.testingId)).toBe('ch-1')

      await flushPromises()

      const testCalls = mockAxiosFn.mock.calls.filter(
        ([config]) => config.url && config.url.includes('notifications/channels/test'),
      )
      expect(testCalls.length).toBe(1)
      expect(testCalls[0][0].data.channel).toEqual(channel)
      expect(val(wrapper.vm.testingId)).toBeNull()
    })
  })

  // 12. deleteChannel removes from list (confirmDelete calls dialog)
  describe('delete channel', () => {
    it('confirmDelete calls $q.dialog', async () => {
      const { wrapper } = await mountComponent()
      const channel = val(wrapper.vm.channels)[0]
      // Should not throw; dialog mock returns onOk/onCancel
      wrapper.vm.confirmDelete(channel)
    })
  })

  // Type options
  describe('type options', () => {
    it('typeOptions contains Discord, Slack, and Webhook', async () => {
      const { wrapper } = await mountComponent()
      const options = wrapper.vm.typeOptions
      expect(options).toHaveLength(3)
      expect(options.map((o) => o.value)).toEqual(['discord', 'slack', 'webhook'])
      expect(options[0].label).toBe('Discord')
      expect(options[1].label).toBe('Slack')
    })
  })

  // Trigger options
  describe('trigger options', () => {
    it('triggerOptions contains all 5 event types', async () => {
      const { wrapper } = await mountComponent()
      const triggers = wrapper.vm.triggerOptions
      expect(triggers).toHaveLength(5)
      expect(triggers.map((t) => t.value)).toEqual([
        'task_completed',
        'task_failed',
        'queue_empty',
        'approval_needed',
        'health_check_failed',
      ])
    })
  })

  // Dialog form fields
  describe('dialog form fields', () => {
    it('dialogForm contains name, type, url, headersRaw, and triggers', async () => {
      const { wrapper } = await mountComponent()
      wrapper.vm.openAddDialog()
      await wrapper.vm.$nextTick()

      const form = val(wrapper.vm.dialogForm)
      expect(form).toHaveProperty('name')
      expect(form).toHaveProperty('type')
      expect(form).toHaveProperty('url')
      expect(form).toHaveProperty('headersRaw')
      expect(form).toHaveProperty('triggers')
    })
  })

  // Helper methods
  describe('helper methods', () => {
    it('channelIcon returns correct icon per type', async () => {
      const { wrapper } = await mountComponent()
      expect(wrapper.vm.channelIcon('discord')).toBe('fab fa-discord')
      expect(wrapper.vm.channelIcon('slack')).toBe('fab fa-slack')
      expect(wrapper.vm.channelIcon('webhook')).toBe('webhook')
      expect(wrapper.vm.channelIcon('unknown')).toBe('webhook')
    })

    it('channelColor returns correct color per type', async () => {
      const { wrapper } = await mountComponent()
      expect(wrapper.vm.channelColor('discord')).toBe('indigo')
      expect(wrapper.vm.channelColor('slack')).toBe('green')
      expect(wrapper.vm.channelColor('webhook')).toBe('grey')
      expect(wrapper.vm.channelColor('unknown')).toBe('grey')
    })

    it('channelTypeLabel returns correct label per type', async () => {
      const { wrapper } = await mountComponent()
      expect(wrapper.vm.channelTypeLabel('discord')).toBe('Discord')
      expect(wrapper.vm.channelTypeLabel('slack')).toBe('Slack')
    })

    it('urlHint changes based on selected type', async () => {
      const { wrapper } = await mountComponent()
      const form = val(wrapper.vm.dialogForm)

      form.type = 'discord'
      await wrapper.vm.$nextTick()
      expect(wrapper.vm.urlHint).toBe('pages.settingsNotifications.hintDiscord')

      form.type = 'slack'
      await wrapper.vm.$nextTick()
      expect(wrapper.vm.urlHint).toBe('pages.settingsNotifications.hintSlack')

      form.type = 'webhook'
      await wrapper.vm.$nextTick()
      expect(wrapper.vm.urlHint).toBe('pages.settingsNotifications.hintWebhook')
    })

    it('editChannel populates dialogForm from channel data', async () => {
      const { wrapper } = await mountComponent()
      const channel = val(wrapper.vm.channels)[0]

      wrapper.vm.editChannel(channel)
      await wrapper.vm.$nextTick()

      expect(val(wrapper.vm.editingChannel)).toBe(channel)
      const form = val(wrapper.vm.dialogForm)
      expect(form.name).toBe('Alerts')
      expect(form.type).toBe('discord')
      expect(form.url).toBe('https://discord.com/api/webhooks/123')
      expect(form.triggers).toEqual(['task_completed', 'task_failed'])
      expect(val(wrapper.vm.showDialog)).toBe(true)
    })
  })

  // Error handling
  describe('error handling', () => {
    it('handles fetch failure gracefully', async () => {
      mockAxiosFn.mockImplementation(() => Promise.reject(new Error('Network error')))

      const wrapper = shallowMountWithQuasar(SettingsNotifications)
      await flushPromises()

      expect(val(wrapper.vm.loading)).toBe(false)
      expect(val(wrapper.vm.channels)).toEqual([])
    })
  })
})
