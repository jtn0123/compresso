import { defineBoot } from '#q-app'
import { createI18n } from 'vue-i18n'
import { LocalStorage } from 'quasar'

type MessageSchema = typeof import('../language/en.json')

// Don't import messages from the directory... Read them from the JSON files in the language directory
//import messages from 'src/i18n'

function loadLocaleInfo(): { messages: Record<string, MessageSchema> } {
  const locales = import.meta.glob<{ default: MessageSchema }>('../language/*.json', { eager: true })
  const messages: Record<string, MessageSchema> = {}
  Object.entries(locales).forEach(([key, module]) => {
    const matched = key.match(/([A-Za-z0-9_-]+)\./i)
    if (matched && matched.length > 1) {
      const locale = matched[1]
      if (locale) messages[locale] = module.default
    }
  })
  return { messages }
}

const { messages } = loadLocaleInfo()

// Read configured local from localStorage
const storedLocale = LocalStorage.getItem('locale')
let configuredLocale = typeof storedLocale === 'string' ? storedLocale : null
if (configuredLocale === null) {
  // Default to English
  configuredLocale = 'en'
}

export default defineBoot(({ app }) => {
  const i18n = createI18n({
    legacy: false,
    locale: configuredLocale,
    fallbackLocale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages,
  })
  // Set i18n instance on app
  app.use(i18n)
})
