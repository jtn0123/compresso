<template>
  <q-select
    v-model="locale"
    :options="localeOptions"
    :label="$t('buttons.language')"
    dense
    borderless
    emit-value
    map-options
    options-dense
    style="min-width: 150px"
  />
</template>

<script lang="ts">
import { LocalStorage } from 'quasar'
import { useI18n } from 'vue-i18n'

// Human-readable labels for known locales.
// Use ISO codes from table: https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes
const LOCALE_LABELS: Record<string, string> = {
  en: 'English',
  mi: 'Maori/te reo Māori',
  zh: 'Chinese/中文',
  nl: 'Dutch/Nederlands',
  fr: 'French/français',
  de: 'German/Deutsch',
  it: 'Italian/Italiano',
  ja: 'Japanese/日本語',
  pl: 'Polish/Polskie',
  'pt-br': 'Portuguese (Brazil)/Português',
  ru: 'Russian/русский',
  es: 'Spanish/Español',
  sv: 'Swedish/Svenska',
}

export default {
  setup() {
    const { locale, availableLocales } = useI18n({ useScope: 'global' })

    // Only offer locales that actually have loaded messages so users can't
    // pick a language that silently falls back to English.
    const localeOptions = availableLocales.map((value) => ({
      value,
      label: LOCALE_LABELS[value] || value,
    }))

    return {
      locale,
      localeOptions,
    }
  },
  watch: {
    locale(lang: string) {
      LocalStorage.set('locale', lang)
    },
  },
}
</script>
